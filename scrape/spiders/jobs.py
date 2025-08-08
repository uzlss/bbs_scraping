# scrape/spiders/jobs.py
import logging
import time
from datetime import date
from pathlib import Path
from urllib.parse import quote_plus

import scrapy
from scrapy import signals
from scrapy.http import Response

from scrape.items import JobItem
from analyze.requirements import extract
from analyze.diagrams import make_all_charts

# catch only parsing empties to retry specifically
try:
    from pandas.errors import EmptyDataError, ParserError
except Exception:  # pandas might not be importable here in some envs; be safe
    EmptyDataError = ParserError = Exception


class JobsSpider(scrapy.Spider):
    name = "jobs"
    handle_httpstatus_list = [400]
    tpr = "r86400"
    start_url = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?"

    def __init__(self, role="Developer", location=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.role = role
        self.location = location
        self.run_dir: Path | None = None
        self.output_file: Path | None = None

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        spider = super().from_crawler(crawler, *args, **kwargs)

        role_slug = spider.role.replace(" ", "_")
        today_str = date.today().isoformat()

        run_dir = Path("data") / role_slug / today_str
        run_dir.mkdir(parents=True, exist_ok=True)

        spider.run_dir = run_dir
        spider.output_file = run_dir / "jobs.csv"

        # Export items into data/<role>/<date>/jobs.csv
        crawler.settings.set(
            "FEEDS",
            {str(spider.output_file): {"format": "csv", "encoding": "utf-8", "overwrite": True}},
            priority="cmdline",
        )

        # Run analytics AFTER feed export finishes.
        feed_signal = getattr(signals, "feedexporter_closed", None) or signals.engine_stopped
        crawler.signals.connect(spider.on_feeds_ready, signal=feed_signal)

        return spider

    def build_url(self, start: int) -> str:
        role_query = quote_plus(self.role)
        url = f"{self.start_url}keywords={role_query}&f_TPR={self.tpr}&start={start}"
        if self.location:
            location_query = quote_plus(self.location)
            url += f"&location={location_query}"
        return url

    async def start(self):
        self.logger.info(f"Spider started (role={self.role}, location={self.location})")
        url = self.build_url(start=0)
        yield scrapy.Request(url=url, callback=self.parse, cb_kwargs={"start": 0})

    def parse(self, response: Response, start: int, **kwargs):  # noqa
        jobs = response.css("li")
        num_jobs = len(jobs)

        if response.status == 400 or not num_jobs:
            self.logger.info(f"No jobs found -> stopping. (start={start})")
            return

        self.logger.info(f"Fetching page (start={start})")
        for job in jobs:
            detail_link = job.css(".base-card__full-link::attr(href)").get(default="").strip()

            item = JobItem(
                title=job.css("h3::text").get(default="not-found").strip(),
                company_name=job.css("h4 a::text").get(default="not-found").strip(),
                location=job.css(".job-search-card__location::text").get(default="").strip(),
                listed_date=job.css("time::attr(datetime)").get(default="").strip(),
                detail_link=detail_link,
                skills=[],
                years_of_experience=None,
            )
            if detail_link:
                yield response.follow(
                    detail_link, callback=self.parse_skills, cb_kwargs={"item": item}
                )

        start += 25
        yield scrapy.Request(
            url=self.build_url(start=start),
            callback=self.parse,
            cb_kwargs={"start": start},
        )

    async def parse_skills(self, response: Response, item: JobItem):
        desc_container = response.css("div.show-more-less-html__markup")
        text_nodes = desc_container.xpath(".//text()").getall()
        cleaned = [t.strip() for t in text_nodes if t.strip()]
        job_description = " ".join(cleaned)

        requirements = await extract(job_description)
        item["skills"] = requirements.get("required_skills", [])
        item["years_of_experience"] = requirements.get("years_experience", 0)
        self.logger.info(f"Returning required skills ({requirements})")
        yield item

    # ---- NEW: run after feeds close ----
    def on_feeds_ready(self, *args, **kwargs):
        """
        Called after feed exporter finished (or after engine stopped if older Scrapy).
        At this point the CSV should be fully written. We still add a short retry loop
        in case of filesystem lag.
        """
        try:
            if not self.output_file or not self.output_file.exists():
                self.logger.warning("No output CSV found — skipping analytics.")
                return

            self.logger.info(f"Running analytics for {self.output_file} -> {self.run_dir}")

            attempts = 10
            delay_s = 0.5
            for i in range(1, attempts + 1):
                try:
                    make_all_charts(
                        str(self.output_file),
                        out_dir=str(self.run_dir),
                        allow_us_state_guess=False,
                    )
                    self.logger.info("Analytics complete.")
                    return
                except (EmptyDataError, ParserError):
                    if i == attempts:
                        raise
                    self.logger.info("CSV not ready to parse yet; retrying (%s/%s)...", i, attempts)
                    time.sleep(delay_s)

        except Exception as e:
            self.logger.exception(f"Analytics failed: {e}")

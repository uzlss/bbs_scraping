import logging

import scrapy
from scrapy.http import Response
from urllib.parse import quote_plus

from scrape.items import JobItem
from analyze.skill import extract_requirements


class JobsSpider(scrapy.Spider):
    name = "jobs"
    tpr = "r86400"  # 86,400 seconds = 1 day
    # allowed_domains = ["linkedin.com", "www.linkedin.com"]
    start_url = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?"

    def __init__(self, role="Developer", location=None, *args, **kwargs):
        super(JobsSpider, self).__init__(*args, **kwargs)
        self.role = role
        self.location = location

    def build_url(self, start: int) -> str:
        role_query = quote_plus(self.role)
        url = f"{self.start_url}keywords={role_query}&f_TPR={self.tpr}&start={start}"
        if self.location:
            location_query = quote_plus(self.location)
            url += f"&location={location_query}"
        return url

    async def start(self):
        logging.info(f"Spider started (role={self.role}, location={self.location})")
        url = self.build_url(start=0)
        yield scrapy.Request(url=url, callback=self.parse, cb_kwargs={"start": 0})

    def parse(self, response: Response, start: int, **kwargs):  # noqa
        jobs = response.css("li")
        num_jobs = len(jobs)

        if not num_jobs:
            logging.info(f"No jobs found -> stopping. (start={start})")
            return

        for job in jobs:
            detail_link = (
                job.css(".base-card__full-link::attr(href)").get(default="").strip()
            )

            item = JobItem(
                title=job.css("h3::text").get(default="not-found").strip(),
                company_name=job.css("h4 a::text").get(default="not-found").strip(),
                location=job.css(".job-search-card__location::text")
                .get(default="not-found")
                .strip(),
                listed_date=job.css("time::attr(datetime)")
                .get(default="not-found")
                .strip(),
                detail_link=detail_link,
                skills=[],
                years_of_experience=None,
            )
            if detail_link:
                yield response.follow(
                    detail_link, callback=self.parse_skills, cb_kwargs={"item": item}
                )

        next_start = start + 25
        logging.info(f"Fetching next page (start={next_start})")
        yield scrapy.Request(
            url=self.build_url(start=next_start),
            callback=self.parse,
            cb_kwargs={"start": next_start},
        )

    def parse_skills(self, response: Response, item: JobItem):
        desc_container = response.css("div.show-more-less-html__markup")
        text_nodes = desc_container.xpath(".//text()").getall()
        cleaned = [t.strip() for t in text_nodes if t.strip()]
        job_description = " ".join(cleaned)
        requirements = extract_requirements(job_description)
        item["skills"] = requirements.get("required_skills", [])
        item["years_of_experience"] = requirements.get("years_experience", 0)
        logging.info(f"Returning required skills ({requirements})")

        yield item

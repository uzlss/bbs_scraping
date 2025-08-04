import logging

import scrapy
from scrapy.http import Response
from urllib.parse import quote_plus

from langdetect import detect, LangDetectException
from nltk.corpus import stopwords
from nltk import word_tokenize, pos_tag, download

from scrape.items import JobItem

"""
Prerequisites:
  pip install nltk langdetect
  python -m nltk.downloader punkt averaged_perceptron_tagger stopwords
NLTK data should be installed once in the environment (not on every import)
"""

class JobsSpider(scrapy.Spider):
    name = "jobs"
    tpr = "r86400"  # 86,400 seconds = 1 day
    allowed_domains = ["linkedin.com", "www.linkedin.com"]
    start_url = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?"

    def __init__(self, role="Developer", location=None, *args, **kwargs):
        super(JobsSpider, self).__init__(*args, **kwargs)
        self.role = role
        self.location = location
        self.stop_words = set(stopwords.words('english'))

    def build_url(self, start: int) -> str:
        role_query = quote_plus(self.role)
        url = f"{self.start_url}keywords={role_query}&f_TPR={self.tpr}&start={start}"
        if self.location:
            location_query = quote_plus(self.location)
            url += f"&location={location_query}"
        return url

    def start_requests(self):
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
                job.css(".base-card__full-link::attr(href)")
                .get(default="")
                .strip()
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
        desc_sel = response.css(
            "div.description__text--rich section.show-more-less-html__markup"
        )
        description = " ".join(desc_sel.css("*::text").getall()).strip()

        # language detection
        try:
            lang = detect(description)
        except LangDetectException:
            return
        if lang != 'en':
            return

        tokens = word_tokenize(description)
        tagged = pos_tag(tokens)
        candidates = [w.lower() for w,p in tagged if p.startswith('NN')]
        skills = [w for w in set(candidates) if w not in self.stop_words and len(w)>1]
        item['skills'] = skills
        yield item

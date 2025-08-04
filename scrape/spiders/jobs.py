import logging

import scrapy
from scrapy.http import Response
from urllib.parse import quote_plus

class JobsSpider(scrapy.Spider):
    name = "jobs"
    allowed_domains = ["www.linkedin.com"]
    start_url = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?"

    def __init__(self, role="Developer", location=None, start=0, *args, **kwargs):
        super(JobsSpider, self).__init__(*args, **kwargs)
        self.role = role
        self.location = location
        self.start = int(start)

    def start_requests(self):
        logging.info("Spider started")

        role_query = quote_plus(self.role)
        url = f"{self.start_url}keywords={role_query}&start={self.start}"

        if self.location:
            location_query = quote_plus(self.location)
            url += f"&location={location_query}"

        yield scrapy.Request(url=url, callback=self.parse)

    def parse(self, response: Response, **kwargs):
        pass
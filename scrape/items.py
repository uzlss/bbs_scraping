# Define here the models for your scraped items
#
# See documentation in:
# https://docs.scrapy.org/en/latest/topics/items.html

import scrapy


class JobItem(scrapy.Item):
    title = scrapy.Field()
    company_name = scrapy.Field()
    location = scrapy.Field()
    listed_date = scrapy.Field()

    detail_link = scrapy.Field()
    skills = scrapy.Field()

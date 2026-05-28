"""
Simple rule-based region inference from a free-text location string.
Returns one of: "remote", "india", "us", "europe", "other", or "" if unknown.
"""

import re

_REMOTE = re.compile(r"\bremote\b", re.I)

_INDIA = re.compile(
    r"\b(india|bengaluru|bangalore|mumbai|delhi|hyderabad|pune|chennai|kolkata"
    r"|noida|gurugram|gurgaon|ahmedabad|in)\b",
    re.I,
)

_US = re.compile(
    r"\b(united states|usa|u\.s\.a|u\.s\.|new york|san francisco|seattle"
    r"|austin|chicago|boston|los angeles|remote.{0,20}us|us.{0,10}only)\b",
    re.I,
)

_EUROPE = re.compile(
    r"\b(europe|european union|eu|uk|united kingdom|germany|france|netherlands"
    r"|berlin|london|amsterdam|paris|remote.{0,20}eu|eu.{0,10}only)\b",
    re.I,
)


def infer_region(location: str) -> str:
    if not location:
        return ""
    if _REMOTE.search(location):
        return "remote"
    if _INDIA.search(location):
        return "india"
    if _US.search(location):
        return "us"
    if _EUROPE.search(location):
        return "europe"
    return "other"

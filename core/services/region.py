"""
Rule-based region inference from a free-text location string.
Returns one of: "remote", "india", "us", "europe", "other", or "" if unknown.

Precedence is remote > india > us > europe > other: an explicitly remote role
stays "remote" (keeps the Remote view populated) even when a city is also named.
Manual correction is available via Job.region_override.
"""

import re

_REMOTE = re.compile(
    r"\b(remote|anywhere|world\s?wide|distributed|work\s?from\s?home|wfh|fully[\s-]?remote|home[\s-]?based)\b",
    re.I,
)

_INDIA = re.compile(
    r"\b(india|bengaluru|bangalore|mumbai|new\s?delhi|delhi|hyderabad|pune|chennai|kolkata|"
    r"noida|gurugram|gurgaon|ahmedabad|jaipur|kochi|indore|chandigarh|coimbatore)\b",
    re.I,
)

_US = re.compile(
    r"(united\s?states|u\.?s\.?a|\busa\b|\bus\b|\bu\.s\.|new\s?york|\bnyc\b|san\s?francisco|"
    r"bay\s?area|silicon\s?valley|seattle|austin|chicago|boston|los\s?angeles|denver|atlanta|"
    r"california|texas|washington|us[-\s]?based|us[-\s]?only|americas)",
    re.I,
)

_EUROPE = re.compile(
    r"\b(europe|european|\beu\b|emea|united\s?kingdom|\buk\b|england|scotland|ireland|dublin|"
    r"germany|france|netherlands|spain|portugal|poland|sweden|switzerland|italy|"
    r"london|berlin|amsterdam|paris|madrid|lisbon|munich|barcelona|warsaw|zurich)\b",
    re.I,
)


def infer_region(location: str) -> str:
    if not location:
        return ""
    text = location.replace("/", " / ").replace("|", " ")  # split smushed multi-locations
    if _REMOTE.search(text):
        return "remote"
    if _INDIA.search(text):
        return "india"
    if _US.search(text):
        return "us"
    if _EUROPE.search(text):
        return "europe"
    return "other"

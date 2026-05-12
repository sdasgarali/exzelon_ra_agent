"""Google Business (Places) lead source adapter for RCM & Digital Marketing LOBs.

Fetches local business listings via Google Places API. Useful for finding
healthcare practices (RCM) and local businesses needing digital marketing.

Requires: GOOGLE_PLACES_API_KEY
"""
import structlog
import requests
from typing import List, Dict, Any, Optional

from app.services.adapters.base import LeadSourceAdapter, RateLimitError

logger = structlog.get_logger()

# Places API (New) text search endpoint
PLACES_URL = "https://places.googleapis.com/v1/places:searchText"


class GoogleBusinessAdapter(LeadSourceAdapter):
    """Adapter for Google Places API (Text Search).

    Searches for businesses by type/keyword and location. Returns business
    name, address, phone, website, rating, and review count.
    """

    def __init__(self, api_key: str = ""):
        self.api_key = api_key
        self._api_calls = 0

    def test_connection(self) -> bool:
        if not self.api_key:
            return False
        try:
            resp = requests.post(
                PLACES_URL,
                headers={
                    "Content-Type": "application/json",
                    "X-Goog-Api-Key": self.api_key,
                    "X-Goog-FieldMask": "places.displayName",
                },
                json={"textQuery": "hospital in New York", "maxResultCount": 1},
                timeout=10,
            )
            self._api_calls += 1
            return resp.status_code == 200
        except Exception:
            return False

    def fetch_leads(
        self,
        query: str = "",
        location: str = "United States",
        limit: int = 20,
        business_type: str = "",
        **kwargs,
    ) -> List[Dict[str, Any]]:
        """Fetch business listings from Google Places.

        Args:
            query: Search query (e.g., "medical practice", "dental clinic")
            location: Location text (e.g., "Houston, TX")
            limit: Max results (API caps at 20 per request)
            business_type: Google place type filter
        """
        if not self.api_key:
            logger.warning("google_business_no_key")
            return []

        leads = []
        search_text = f"{query} in {location}" if query else f"business in {location}"
        max_results = min(limit, 20)  # API max per request

        field_mask = (
            "places.displayName,places.formattedAddress,places.nationalPhoneNumber,"
            "places.websiteUri,places.rating,places.userRatingCount,"
            "places.businessStatus,places.types,places.googleMapsUri,"
            "places.addressComponents"
        )

        body = {
            "textQuery": search_text,
            "maxResultCount": max_results,
            "languageCode": "en",
        }

        if business_type:
            body["includedType"] = business_type

        try:
            resp = requests.post(
                PLACES_URL,
                headers={
                    "Content-Type": "application/json",
                    "X-Goog-Api-Key": self.api_key,
                    "X-Goog-FieldMask": field_mask,
                },
                json=body,
                timeout=30,
            )
            self._api_calls += 1

            if resp.status_code == 429:
                raise RateLimitError("Google Places rate limit", partial_results=leads)
            resp.raise_for_status()
            data = resp.json()
        except RateLimitError:
            raise
        except Exception as e:
            logger.error("google_business_fetch_error", error=str(e))
            return leads

        places = data.get("places") or []
        for place in places:
            normalized = self.normalize(place)
            if normalized:
                leads.append(normalized)

        logger.info("google_business_fetched", count=len(leads), query=query)
        return leads

    def normalize(self, raw_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Normalize Google Place to standard lead format."""
        try:
            display_name = raw_data.get("displayName", {})
            name = display_name.get("text", "") if isinstance(display_name, dict) else str(display_name)
            if not name:
                return None

            address = raw_data.get("formattedAddress", "")
            phone = raw_data.get("nationalPhoneNumber", "")
            website = raw_data.get("websiteUri", "")
            rating = raw_data.get("rating")
            review_count = raw_data.get("userRatingCount", 0)
            maps_url = raw_data.get("googleMapsUri", "")
            business_status = raw_data.get("businessStatus", "")
            types = raw_data.get("types", [])

            # Extract state and city from addressComponents
            state = ""
            city = ""
            for component in raw_data.get("addressComponents", []):
                comp_types = component.get("types", [])
                if "administrative_area_level_1" in comp_types:
                    state = component.get("shortText", "")
                elif "locality" in comp_types:
                    city = component.get("longText", "")

            # Extract domain from website
            domain = ""
            if website:
                from urllib.parse import urlparse
                parsed = urlparse(website)
                domain = parsed.netloc.replace("www.", "")

            # Skip permanently closed businesses
            if business_status == "CLOSED_PERMANENTLY":
                return None

            # Determine industry from place types
            industry = _infer_industry(types)

            return {
                "client_name": name,
                "industry": industry,
                "state": state,
                "city": city,
                "domain": domain,
                "source": "google_business",
                "source_url": maps_url,
                "job_title": industry or "Local Business",
                "job_link": maps_url or website,
                "posting_date": None,
                "employer_website": website,
                "contact_phone": phone or None,
                "metadata": {
                    "rating": rating,
                    "review_count": review_count,
                    "business_status": business_status,
                    "place_types": types[:5],
                    "address": address,
                    "website": website,
                },
            }
        except Exception as e:
            logger.warning("google_business_normalize_error", error=str(e))
            return None

    @property
    def source_name(self) -> str:
        return "google_business"


def _infer_industry(types: List[str]) -> str:
    """Infer industry from Google Place types."""
    type_set = set(types)
    if type_set & {"hospital", "doctor", "dentist", "health", "pharmacy", "physiotherapist"}:
        return "Healthcare"
    if type_set & {"restaurant", "food", "cafe", "bakery", "bar"}:
        return "Food & Beverage"
    if type_set & {"store", "shopping_mall", "clothing_store", "shoe_store"}:
        return "Retail"
    if type_set & {"gym", "spa", "beauty_salon", "hair_care"}:
        return "Health & Wellness"
    if type_set & {"lawyer", "accounting", "insurance_agency", "real_estate_agency"}:
        return "Professional Services"
    if type_set & {"car_dealer", "car_repair", "car_wash"}:
        return "Automotive"
    if type_set & {"school", "university"}:
        return "Education"
    if type_set & {"lodging", "hotel"}:
        return "Hospitality"
    return "Local Business"

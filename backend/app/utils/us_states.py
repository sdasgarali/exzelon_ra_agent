"""US city-to-state mapping for lead sourcing location resolution."""

# Top ~300 US cities mapped to 2-letter state codes
_CITY_STATE_MAP: dict[str, str] = {
    # Alabama
    "birmingham": "AL", "montgomery": "AL", "huntsville": "AL", "mobile": "AL", "tuscaloosa": "AL",
    # Alaska
    "anchorage": "AK", "fairbanks": "AK", "juneau": "AK",
    # Arizona
    "phoenix": "AZ", "tucson": "AZ", "mesa": "AZ", "scottsdale": "AZ", "chandler": "AZ",
    "tempe": "AZ", "gilbert": "AZ", "glendale": "AZ", "peoria": "AZ",
    # Arkansas
    "little rock": "AR", "fayetteville": "AR", "fort smith": "AR",
    # California
    "los angeles": "CA", "san francisco": "CA", "san diego": "CA", "san jose": "CA",
    "sacramento": "CA", "fresno": "CA", "oakland": "CA", "long beach": "CA",
    "bakersfield": "CA", "anaheim": "CA", "santa ana": "CA", "riverside": "CA",
    "stockton": "CA", "irvine": "CA", "santa clara": "CA", "fremont": "CA",
    "palo alto": "CA", "mountain view": "CA", "sunnyvale": "CA", "cupertino": "CA",
    "burbank": "CA", "pasadena": "CA", "redwood city": "CA", "menlo park": "CA",
    "santa monica": "CA", "beverly hills": "CA", "san mateo": "CA", "torrance": "CA",
    "el segundo": "CA", "culver city": "CA", "walnut creek": "CA", "pleasanton": "CA",
    # Colorado
    "denver": "CO", "colorado springs": "CO", "aurora": "CO", "boulder": "CO",
    "fort collins": "CO", "lakewood": "CO", "broomfield": "CO",
    # Connecticut
    "hartford": "CT", "new haven": "CT", "stamford": "CT", "bridgeport": "CT",
    "norwalk": "CT", "danbury": "CT", "greenwich": "CT",
    # Delaware
    "wilmington": "DE", "dover": "DE", "newark": "DE",
    # Florida
    "miami": "FL", "orlando": "FL", "tampa": "FL", "jacksonville": "FL",
    "st. petersburg": "FL", "fort lauderdale": "FL", "tallahassee": "FL",
    "hialeah": "FL", "cape coral": "FL", "boca raton": "FL", "west palm beach": "FL",
    "clearwater": "FL", "naples": "FL", "sarasota": "FL", "pensacola": "FL",
    "fort myers": "FL", "gainesville": "FL", "daytona beach": "FL",
    # Georgia
    "atlanta": "GA", "savannah": "GA", "augusta": "GA", "columbus": "GA",
    "athens": "GA", "macon": "GA", "roswell": "GA", "alpharetta": "GA",
    "sandy springs": "GA", "marietta": "GA",
    # Hawaii
    "honolulu": "HI",
    # Idaho
    "boise": "ID", "nampa": "ID", "meridian": "ID",
    # Illinois
    "chicago": "IL", "aurora": "IL", "naperville": "IL", "rockford": "IL",
    "springfield": "IL", "peoria": "IL", "champaign": "IL", "evanston": "IL",
    "schaumburg": "IL", "deerfield": "IL", "lake forest": "IL",
    # Indiana
    "indianapolis": "IN", "fort wayne": "IN", "evansville": "IN", "south bend": "IN",
    "carmel": "IN", "fishers": "IN",
    # Iowa
    "des moines": "IA", "cedar rapids": "IA", "davenport": "IA", "iowa city": "IA",
    # Kansas
    "wichita": "KS", "overland park": "KS", "kansas city": "KS", "topeka": "KS",
    "olathe": "KS",
    # Kentucky
    "louisville": "KY", "lexington": "KY", "bowling green": "KY",
    # Louisiana
    "new orleans": "LA", "baton rouge": "LA", "shreveport": "LA", "lafayette": "LA",
    # Maine
    "portland": "ME", "bangor": "ME",
    # Maryland
    "baltimore": "MD", "columbia": "MD", "silver spring": "MD", "rockville": "MD",
    "bethesda": "MD", "annapolis": "MD", "frederick": "MD",
    # Massachusetts
    "boston": "MA", "cambridge": "MA", "worcester": "MA", "springfield": "MA",
    "lowell": "MA", "quincy": "MA", "newton": "MA", "somerville": "MA",
    "waltham": "MA", "burlington": "MA", "framingham": "MA", "lexington": "MA",
    # Michigan
    "detroit": "MI", "grand rapids": "MI", "ann arbor": "MI", "lansing": "MI",
    "dearborn": "MI", "troy": "MI", "warren": "MI", "sterling heights": "MI",
    # Minnesota
    "minneapolis": "MN", "st. paul": "MN", "saint paul": "MN", "rochester": "MN",
    "duluth": "MN", "bloomington": "MN", "eden prairie": "MN", "plymouth": "MN",
    # Mississippi
    "jackson": "MS", "gulfport": "MS",
    # Missouri
    "kansas city": "MO", "st. louis": "MO", "saint louis": "MO", "springfield": "MO",
    "columbia": "MO",
    # Montana
    "billings": "MT", "missoula": "MT",
    # Nebraska
    "omaha": "NE", "lincoln": "NE",
    # Nevada
    "las vegas": "NV", "reno": "NV", "henderson": "NV",
    # New Hampshire
    "manchester": "NH", "concord": "NH", "nashua": "NH",
    # New Jersey
    "newark": "NJ", "jersey city": "NJ", "trenton": "NJ", "princeton": "NJ",
    "hoboken": "NJ", "paramus": "NJ", "parsippany": "NJ", "edison": "NJ",
    "cherry hill": "NJ", "morristown": "NJ",
    # New Mexico
    "albuquerque": "NM", "santa fe": "NM", "las cruces": "NM",
    # New York
    "new york": "NY", "new york city": "NY", "nyc": "NY", "manhattan": "NY",
    "brooklyn": "NY", "buffalo": "NY", "rochester": "NY", "albany": "NY",
    "syracuse": "NY", "white plains": "NY", "yonkers": "NY",
    # North Carolina
    "charlotte": "NC", "raleigh": "NC", "greensboro": "NC", "durham": "NC",
    "winston-salem": "NC", "asheville": "NC", "cary": "NC", "research triangle park": "NC",
    # North Dakota
    "fargo": "ND", "bismarck": "ND",
    # Ohio
    "columbus": "OH", "cleveland": "OH", "cincinnati": "OH", "toledo": "OH",
    "akron": "OH", "dayton": "OH", "dublin": "OH",
    # Oklahoma
    "oklahoma city": "OK", "tulsa": "OK", "norman": "OK",
    # Oregon
    "portland": "OR", "salem": "OR", "eugene": "OR", "beaverton": "OR",
    "hillsboro": "OR", "bend": "OR",
    # Pennsylvania
    "philadelphia": "PA", "pittsburgh": "PA", "allentown": "PA", "harrisburg": "PA",
    "king of prussia": "PA", "malvern": "PA", "conshohocken": "PA",
    "wayne": "PA", "erie": "PA",
    # Rhode Island
    "providence": "RI", "warwick": "RI", "cranston": "RI",
    # South Carolina
    "charleston": "SC", "columbia": "SC", "greenville": "SC",
    # South Dakota
    "sioux falls": "SD", "rapid city": "SD",
    # Tennessee
    "nashville": "TN", "memphis": "TN", "knoxville": "TN", "chattanooga": "TN",
    "franklin": "TN",
    # Texas
    "houston": "TX", "dallas": "TX", "austin": "TX", "san antonio": "TX",
    "fort worth": "TX", "el paso": "TX", "arlington": "TX", "plano": "TX",
    "irving": "TX", "frisco": "TX", "mckinney": "TX", "round rock": "TX",
    "the woodlands": "TX", "sugar land": "TX", "richardson": "TX", "addison": "TX",
    # Utah
    "salt lake city": "UT", "provo": "UT", "ogden": "UT", "lehi": "UT",
    "draper": "UT", "sandy": "UT",
    # Vermont
    "burlington": "VT",
    # Virginia
    "richmond": "VA", "virginia beach": "VA", "norfolk": "VA", "arlington": "VA",
    "alexandria": "VA", "reston": "VA", "mclean": "VA", "tysons": "VA",
    "fairfax": "VA", "herndon": "VA", "charlottesville": "VA",
    # Washington
    "seattle": "WA", "tacoma": "WA", "spokane": "WA", "bellevue": "WA",
    "redmond": "WA", "kirkland": "WA", "olympia": "WA",
    # Washington DC
    "washington": "DC", "washington dc": "DC", "washington d.c.": "DC",
    # West Virginia
    "charleston": "WV", "morgantown": "WV",
    # Wisconsin
    "milwaukee": "WI", "madison": "WI", "green bay": "WI",
    # Wyoming
    "cheyenne": "WY", "casper": "WY",
}

# Full state name → 2-letter code
_STATE_NAME_MAP: dict[str, str] = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
    "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK",
    "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
    "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
    "vermont": "VT", "virginia": "VA", "washington": "WA", "west virginia": "WV",
    "wisconsin": "WI", "wyoming": "WY", "district of columbia": "DC",
}


def city_to_state(city: str) -> str | None:
    """Look up 2-letter state code from city name. Returns None if not found."""
    if not city:
        return None
    return _CITY_STATE_MAP.get(city.strip().lower())


def normalize_state(raw: str) -> str:
    """Normalize a state value to 2-letter code.

    Handles full names ('California' → 'CA'), already-abbreviated ('CA' → 'CA'),
    and mixed case.
    """
    if not raw:
        return ""
    cleaned = raw.strip()
    # Already 2-letter code
    if len(cleaned) == 2 and cleaned.isalpha():
        return cleaned.upper()
    # Full state name
    code = _STATE_NAME_MAP.get(cleaned.lower())
    if code:
        return code
    return ""

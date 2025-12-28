"""
Exhaustive genre classification rules for Spotify.

This module contains comprehensive mappings of Spotify genre tags to broad categories.
Used by both the sync script and notebooks for consistent genre classification.
"""

from typing import Optional, List

# Genre classification rules for split playlists (HipHop/Dance/Other)
# Exhaustive list of Spotify genre tags
GENRE_SPLIT_RULES = {
    "HipHop": [
        # Core hip hop
        "hip hop", "rap", "trap", "drill", "grime", "crunk", "phonk",
        "boom bap", "dirty south", "gangsta", "melodic rap",
        # Regional
        "uk drill", "uk hip hop", "uk rap", "chicago drill", "brooklyn drill",
        "atlanta hip hop", "southern hip hop", "east coast hip hop", "west coast hip hop",
        "memphis hip hop", "houston rap", "detroit hip hop", "miami bass",
        "french hip hop", "german hip hop", "australian hip hop", "canadian hip hop",
        # Subgenres
        "conscious hip hop", "underground hip hop", "alternative hip hop",
        "experimental hip hop", "abstract hip hop", "political hip hop",
        "jazz rap", "lo-fi hip hop", "cloud rap", "emo rap", "rage rap",
        "plugg", "pluggnb", "hyperpop rap", "glitch hop",
        # Era/style specific
        "old school hip hop", "golden age hip hop", "new school hip hop",
        "mumble rap", "lyrical rap", "battle rap", "horrorcore",
        "chopped and screwed", "hyphy", "snap music", "bounce",
        # Related
        "g-funk", "gangster rap", "hardcore hip hop", "mafioso rap",
        "nerdcore", "christian hip hop", "gospel rap",
        "afro trap", "latin trap", "reggaeton trap",
    ],
    "Dance": [
        # House
        "house", "deep house", "tech house", "progressive house", "future house",
        "bass house", "electro house", "big room", "tropical house", "melodic house",
        "afro house", "soulful house", "funky house", "disco house", "french house",
        "chicago house", "acid house", "minimal house", "microhouse",
        # Techno
        "techno", "minimal techno", "detroit techno", "dub techno", "acid techno",
        "hard techno", "industrial techno", "melodic techno", "peak time techno",
        # Trance
        "trance", "progressive trance", "uplifting trance", "vocal trance",
        "psytrance", "goa trance", "hard trance", "tech trance", "acid trance",
        # Bass music
        "dubstep", "brostep", "riddim", "melodic dubstep", "future bass",
        "drum and bass", "liquid dnb", "jungle", "neurofunk", "jump up",
        "breakbeat", "uk breakbeat", "big beat",
        # EDM/Festival
        "edm", "electronic", "electronica", "dance", "dance pop",
        "complextro", "moombahton", "trap edm", "festival",
        # Garage/UK
        "uk garage", "2-step", "speed garage", "bassline", "uk bass",
        "grime", "uk funky", "jersey club",
        # Hardcore/Hard dance
        "hardstyle", "hardcore", "gabber", "happy hardcore", "frenchcore",
        "hard dance", "hard trance", "hard house", "jumpstyle",
        # Ambient/Downtempo
        "ambient", "downtempo", "chillout", "chillwave", "lo-fi beats",
        "trip hop", "dub", "idm", "glitch",
        # Synth
        "synthwave", "retrowave", "darksynth", "outrun", "vaporwave",
        "synthpop", "electropop", "eurodance", "italo disco",
        # Other electronic
        "electro", "electro swing", "nu disco", "disco", "space disco",
        "leftfield", "experimental electronic", "industrial",
    ]
}

# Categories for split playlists
SPLIT_GENRES = ["HipHop", "Dance", "Other"]

# Broad genre classification for master playlists
# Exhaustive mapping of Spotify genres to broad categories
GENRE_RULES = [
    # Hip-Hop / Rap
    ([
        "hip hop", "rap", "trap", "drill", "grime", "crunk", "boom bap", "dirty south", "phonk",
        "uk drill", "uk hip hop", "uk rap", "chicago drill", "brooklyn drill",
        "atlanta hip hop", "southern hip hop", "east coast hip hop", "west coast hip hop",
        "memphis hip hop", "houston rap", "detroit hip hop", "miami bass",
        "conscious hip hop", "underground hip hop", "alternative hip hop",
        "experimental hip hop", "jazz rap", "cloud rap", "emo rap", "rage rap",
        "plugg", "pluggnb", "old school hip hop", "golden age hip hop",
        "mumble rap", "lyrical rap", "battle rap", "horrorcore",
        "chopped and screwed", "hyphy", "snap music", "bounce",
        "g-funk", "gangster rap", "hardcore hip hop", "mafioso rap",
        "nerdcore", "afro trap", "latin trap",
    ], "Hip-Hop"),
    
    # R&B / Soul
    ([
        "r&b", "rnb", "soul", "neo soul", "funk", "motown", "disco",
        "contemporary r&b", "alternative r&b", "new jack swing",
        "quiet storm", "urban contemporary", "rhythm and blues",
        "psychedelic soul", "northern soul", "southern soul", "blue-eyed soul",
        "philly soul", "memphis soul", "chicago soul", "deep funk",
        "p-funk", "go-go", "boogie", "electrofunk",
        "gospel", "christian", "worship", "ccm",
    ], "R&B/Soul"),
    
    # Electronic / Dance
    ([
        "electronic", "edm", "house", "techno", "trance", "dubstep", "drum and bass",
        "deep house", "tech house", "progressive house", "future house", "bass house",
        "electro house", "big room", "tropical house", "melodic house",
        "minimal techno", "detroit techno", "dub techno", "melodic techno",
        "progressive trance", "uplifting trance", "psytrance", "goa trance",
        "future bass", "liquid dnb", "jungle", "neurofunk",
        "breakbeat", "uk garage", "bassline", "uk bass",
        "hardstyle", "hardcore", "gabber", "happy hardcore",
        "ambient", "downtempo", "chillout", "trip hop", "idm",
        "synthwave", "retrowave", "vaporwave", "electropop",
        "electro", "electro swing", "nu disco", "eurodance",
    ], "Electronic"),
    
    # Rock
    ([
        "rock", "alternative", "grunge", "punk", "emo", "post-punk", "shoegaze",
        "alternative rock", "indie rock", "hard rock", "classic rock", "soft rock",
        "progressive rock", "psychedelic rock", "art rock", "experimental rock",
        "garage rock", "surf rock", "blues rock", "southern rock",
        "punk rock", "pop punk", "hardcore punk", "post-hardcore", "skate punk",
        "emo", "screamo", "midwest emo", "emo pop",
        "grunge", "noise rock", "stoner rock", "desert rock",
        "post-rock", "math rock", "noise", "industrial rock",
        "new wave", "post-punk revival", "gothic rock", "darkwave",
        "britpop", "madchester", "jangle pop", "power pop",
    ], "Rock"),
    
    # Metal
    ([
        "metal", "heavy metal", "death metal", "black metal", "thrash",
        "thrash metal", "speed metal", "power metal", "progressive metal",
        "doom metal", "sludge metal", "stoner metal", "drone metal",
        "death metal", "melodic death metal", "technical death metal", "deathcore",
        "black metal", "atmospheric black metal", "symphonic black metal",
        "metalcore", "melodic metalcore", "djent", "nu metal", "rap metal",
        "symphonic metal", "gothic metal", "folk metal", "viking metal",
        "industrial metal", "groove metal", "glam metal", "hair metal",
        "grindcore", "goregrind", "mathcore", "chaotic hardcore",
    ], "Metal"),
    
    # Indie / Alternative
    ([
        "indie", "indie rock", "indie pop", "lo-fi", "dream pop",
        "indie folk", "indie electronic", "indietronica",
        "bedroom pop", "art pop", "chamber pop", "baroque pop",
        "folktronica", "freak folk", "anti-folk",
        "slowcore", "sadcore", "shoegaze", "nu gaze",
        "chillwave", "glo-fi", "hypnagogic pop",
        "twee pop", "c86", "sarah records",
    ], "Indie"),
    
    # Pop
    ([
        "pop", "dance pop", "synth pop", "electropop", "hyperpop",
        "teen pop", "bubblegum pop", "europop", "latin pop",
        "k-pop", "j-pop", "c-pop", "mandopop", "cantopop",
        "art pop", "experimental pop", "avant-pop",
        "adult contemporary", "soft rock", "easy listening",
        "boy band", "girl group", "idol",
    ], "Pop"),
    
    # Latin
    ([
        "latin", "reggaeton", "salsa", "bachata", "cumbia",
        "latin pop", "latin hip hop", "latin trap", "urbano latino",
        "dembow", "perreo", "moombahton",
        "merengue", "vallenato", "norteño", "banda", "corridos",
        "tango", "flamenco", "bossa nova", "samba", "mpb",
        "latin rock", "rock en español", "latin alternative",
        "mariachi", "ranchera", "bolero", "son cubano",
        "salsa", "timba", "mambo", "cha-cha-cha",
        "brazilian", "forró", "axé", "pagode", "sertanejo",
    ], "Latin"),
    
    # African / Caribbean / World
    ([
        "afrobeat", "afrobeats", "afropop", "afro house", "amapiano",
        "highlife", "juju", "fuji", "afro funk", "afro soul",
        "reggae", "dancehall", "dub", "roots reggae", "lovers rock",
        "ska", "rocksteady", "ragga", "bashment",
        "soca", "calypso", "chutney", "zouk", "kompa",
        "world", "world music", "global", "ethnic", "traditional",
        "african", "west african", "east african", "south african",
        "kwaito", "gqom", "shangaan electro", "township",
        "arabic", "middle eastern", "persian", "turkish",
        "indian", "bollywood", "bhangra", "filmi", "desi",
        "asian", "chinese", "japanese", "korean", "vietnamese",
    ], "World"),
    
    # Jazz
    ([
        "jazz", "smooth jazz", "bebop", "swing", "big band",
        "cool jazz", "hard bop", "modal jazz", "free jazz",
        "fusion", "jazz fusion", "jazz funk", "acid jazz",
        "vocal jazz", "jazz vocal", "jazz blues",
        "latin jazz", "afro-cuban jazz", "bossa nova",
        "contemporary jazz", "modern jazz", "nu jazz",
        "avant-garde jazz", "experimental jazz",
        "dixieland", "new orleans jazz", "ragtime",
        "soul jazz", "jazz soul", "spiritual jazz",
    ], "Jazz"),
    
    # Classical
    ([
        "classical", "orchestra", "symphony", "opera",
        "baroque", "romantic", "classical period", "modern classical",
        "contemporary classical", "minimalism", "post-minimalism",
        "chamber music", "string quartet", "piano", "violin",
        "orchestral", "symphonic", "philharmonic",
        "choral", "choir", "a cappella", "gregorian",
        "opera", "operetta", "musical theater", "broadway",
        "soundtrack", "film score", "cinematic",
        "neoclassical", "neo-romantic", "avant-garde classical",
    ], "Classical"),
    
    # Country / Folk / Americana
    ([
        "country", "folk", "americana", "bluegrass",
        "country pop", "country rock", "alt-country", "outlaw country",
        "contemporary country", "traditional country", "honky tonk",
        "nashville sound", "countrypolitan", "bro-country",
        "folk rock", "contemporary folk", "traditional folk",
        "singer-songwriter", "acoustic", "unplugged",
        "bluegrass", "newgrass", "progressive bluegrass",
        "old-time", "appalachian", "mountain music",
        "celtic", "irish", "scottish", "english folk",
        "nordic", "scandinavian", "viking",
    ], "Country/Folk"),
    
    # Blues
    ([
        "blues", "electric blues", "acoustic blues", "delta blues",
        "chicago blues", "texas blues", "west coast blues",
        "blues rock", "modern blues", "contemporary blues",
        "soul blues", "rhythm and blues", "jump blues",
        "country blues", "piedmont blues", "swamp blues",
    ], "Blues"),
]


def get_split_genre(genre_list: list, include_other: bool = True) -> Optional[str]:
    """Map artist genres to HipHop, Dance, or Other.
    
    Args:
        genre_list: List of genre strings from artist
        include_other: If True, return "Other" for unmatched; else return None
    
    Returns:
        "HipHop" - for hip hop, rap, trap, drill, etc.
        "Dance" - for electronic, EDM, house, techno, etc.
        "Other" - for everything else (rock, pop, indie, r&b, etc.)
        None - if include_other=False and no match
    """
    if not genre_list:
        return "Other" if include_other else None
    combined = " ".join(str(g) for g in genre_list).lower()
    for genre_name, keywords in GENRE_SPLIT_RULES.items():
        if any(kw in combined for kw in keywords):
            return genre_name
    return "Other" if include_other else None


def get_broad_genre(genre_list: list) -> Optional[str]:
    """Map artist genres to broad category for master playlists.
    
    Args:
        genre_list: List of genre strings from artist
    
    Returns:
        Broad genre category (e.g., "Hip-Hop", "Electronic", "Rock") or None
    """
    if not genre_list:
        return None
    combined = " ".join(str(g) for g in genre_list).lower()
    for keywords, category in GENRE_RULES:
        if any(kw in combined for kw in keywords):
            return category
    return None


def get_all_split_genres(genre_list: list, include_other: bool = True) -> List[str]:
    """Map artist genres to ALL matching split genres (HipHop, Dance, Other).
    
    A track/artist can match multiple categories.
    "Other" is assigned only if genres don't match HipHop or Dance.
    
    Args:
        genre_list: List of genre strings from artist
        include_other: If True, include "Other" if no HipHop/Dance matches; else return empty list
    
    Returns:
        List of matching genres: Can be ["HipHop"], ["Dance"], ["HipHop", "Dance"], or ["Other"]
    """
    if not genre_list:
        return ["Other"] if include_other else []
    
    combined = " ".join(str(g) for g in genre_list).lower()
    matched = []
    
    # Check for HipHop and Dance matches (explicit categories)
    for genre_name in ["HipHop", "Dance"]:
        if genre_name in GENRE_SPLIT_RULES:
            keywords = GENRE_SPLIT_RULES[genre_name]
            if any(kw in combined for kw in keywords):
                matched.append(genre_name)
    
    # Only add "Other" if we didn't match HipHop or Dance
    if not matched and include_other:
        matched.append("Other")
    
    return matched


def get_all_broad_genres(genre_list: list) -> List[str]:
    """Map artist genres to ALL matching broad categories.
    
    A track/artist can match multiple categories (e.g., both Hip-Hop and R&B/Soul).
    
    Args:
        genre_list: List of genre strings from artist
    
    Returns:
        List of matching broad genre categories
    """
    if not genre_list:
        return []
    
    combined = " ".join(str(g) for g in genre_list).lower()
    matched = []
    seen = set()
    
    for keywords, category in GENRE_RULES:
        if category not in seen and any(kw in combined for kw in keywords):
            matched.append(category)
            seen.add(category)
    
    return matched


# All broad genre categories
ALL_BROAD_GENRES = [category for _, category in GENRE_RULES]


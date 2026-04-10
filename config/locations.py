"""
Representive delivery addresses for competitive intelligence scraping.
25 locations in CDMX + 2 secondary cities covering 5 socioeconomic levels.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class Location:
    """A delivery address with metadata for scraping."""
    id: str
    address: str
    colonia: str
    alcaldia: str
    city: str
    lat: float
    lng: float
    zone_type: str       # high_income, medium_high_income, medium_income, low_income, commercial
    zone_label: str      # Human-readable zone label
    priority: int        # 1 = always scrape, 2 = full run, 3 = bonus

    @property
    def short_name(self) -> str:
        return f"{self.colonia}, {self.alcaldia}"


# ============================================================
# All locations
# ============================================================

LOCATIONS: list[Location] = [
    # ----- HIGH INCOME (5) -----
    Location(
        id="polanco",
        address="Av. Presidente Masaryk 340, Polanco V Sección, Miguel Hidalgo, CDMX",
        colonia="Polanco V Sección",
        alcaldia="Miguel Hidalgo",
        city="CDMX",
        lat=19.4326,
        lng=-99.1942,
        zone_type="high_income",
        zone_label="Polanco",
        priority=1,
    ),
    Location(
        id="santa_fe",
        address="Av. Santa Fe 440, Santa Fe, Cuajimalpa, CDMX",
        colonia="Santa Fe",
        alcaldia="Cuajimalpa",
        city="CDMX",
        lat=19.3592,
        lng=-99.2741,
        zone_type="high_income",
        zone_label="Santa Fe",
        priority=1,
    ),
    Location(
        id="condesa",
        address="Ámsterdam 240, Hipódromo, Cuauhtémoc, CDMX",
        colonia="Condesa",
        alcaldia="Cuauhtémoc",
        city="CDMX",
        lat=19.4113,
        lng=-99.1722,
        zone_type="high_income",
        zone_label="Condesa",
        priority=1,
    ),
    Location(
        id="roma_norte",
        address="Av. Álvaro Obregón 120, Roma Norte, Cuauhtémoc, CDMX",
        colonia="Roma Norte",
        alcaldia="Cuauhtémoc",
        city="CDMX",
        lat=19.4195,
        lng=-99.1619,
        zone_type="high_income",
        zone_label="Roma Norte",
        priority=2,
    ),
    Location(
        id="lomas",
        address="Blvd. Manuel Ávila Camacho 40, Lomas de Chapultepec, Miguel Hidalgo, CDMX",
        colonia="Lomas de Chapultepec",
        alcaldia="Miguel Hidalgo",
        city="CDMX",
        lat=19.4251,
        lng=-99.2117,
        zone_type="high_income",
        zone_label="Lomas de Chapultepec",
        priority=2,
    ),

    # ----- MEDIUM-HIGH INCOME (5) -----
    Location(
        id="del_valle",
        address="Av. Universidad 1200, Del Valle Centro, Benito Juárez, CDMX",
        colonia="Del Valle Centro",
        alcaldia="Benito Juárez",
        city="CDMX",
        lat=19.3846,
        lng=-99.1736,
        zone_type="medium_high_income",
        zone_label="Del Valle",
        priority=1,
    ),
    Location(
        id="del_valle_sur",
        address="Av. Coyoacán 1500, Del Valle Sur, Benito Juárez, CDMX",
        colonia="Del Valle Sur",
        alcaldia="Benito Juárez",
        city="CDMX",
        lat=19.3723,
        lng=-99.1667,
        zone_type="medium_high_income",
        zone_label="Del Valle Sur",
        priority=2,
    ),
    Location(
        id="country_club",
        address="Calz. de Tlalpan 2000, Country Club, Coyoacán, CDMX",
        colonia="Country Club",
        alcaldia="Coyoacán",
        city="CDMX",
        lat=19.3594,
        lng=-99.1534,
        zone_type="medium_high_income",
        zone_label="Coyoacán",
        priority=2,
    ),
    Location(
        id="florida",
        address="Insurgentes Sur 1800, Florida, Álvaro Obregón, CDMX",
        colonia="Florida",
        alcaldia="Álvaro Obregón",
        city="CDMX",
        lat=19.3645,
        lng=-99.1871,
        zone_type="medium_high_income",
        zone_label="Insurgentes Sur",
        priority=2,
    ),
    Location(
        id="mixcoac",
        address="Av. Revolución 1300, Mixcoac, Benito Juárez, CDMX",
        colonia="Mixcoac",
        alcaldia="Benito Juárez",
        city="CDMX",
        lat=19.3768,
        lng=-99.1872,
        zone_type="medium_high_income",
        zone_label="Mixcoac",
        priority=2,
    ),

    # ----- MEDIUM INCOME (5) -----
    Location(
        id="narvarte",
        address="Eje Central 500, Narvarte Poniente, Benito Juárez, CDMX",
        colonia="Narvarte Poniente",
        alcaldia="Benito Juárez",
        city="CDMX",
        lat=19.3960,
        lng=-99.1496,
        zone_type="medium_income",
        zone_label="Narvarte",
        priority=1,
    ),
    Location(
        id="narvarte_ote",
        address="Av. Cuauhtémoc 800, Narvarte Oriente, Benito Juárez, CDMX",
        colonia="Narvarte Oriente",
        alcaldia="Benito Juárez",
        city="CDMX",
        lat=19.3915,
        lng=-99.1440,
        zone_type="medium_income",
        zone_label="Narvarte Oriente",
        priority=2,
    ),
    Location(
        id="agricola_oriental",
        address="Calz. Ignacio Zaragoza 600, Agrícola Oriental, Iztacalco, CDMX",
        colonia="Agrícola Oriental",
        alcaldia="Iztacalco",
        city="CDMX",
        lat=19.3965,
        lng=-99.0863,
        zone_type="medium_income",
        zone_label="Agrícola Oriental",
        priority=2,
    ),
    Location(
        id="letran_valle",
        address="Eje 5 Sur 300, Letrán Valle, Benito Juárez, CDMX",
        colonia="Letrán Valle",
        alcaldia="Benito Juárez",
        city="CDMX",
        lat=19.3750,
        lng=-99.1570,
        zone_type="medium_income",
        zone_label="Letrán Valle",
        priority=2,
    ),
    Location(
        id="tacuba",
        address="Calz. México-Tacuba 500, Tacuba, Miguel Hidalgo, CDMX",
        colonia="Tacuba",
        alcaldia="Miguel Hidalgo",
        city="CDMX",
        lat=19.4520,
        lng=-99.1800,
        zone_type="medium_income",
        zone_label="Tacuba",
        priority=2,
    ),

    # ----- LOW INCOME / PERIPHERAL (5) -----
    Location(
        id="iztapalapa",
        address="Av. Ermita Iztapalapa 3000, Santa Cruz Meyehualco, Iztapalapa, CDMX",
        colonia="Santa Cruz Meyehualco",
        alcaldia="Iztapalapa",
        city="CDMX",
        lat=19.3579,
        lng=-99.0520,
        zone_type="low_income",
        zone_label="Iztapalapa",
        priority=1,
    ),
    Location(
        id="tlahuac",
        address="Av. Tláhuac 4000, Santiago Acahualtepec, Iztapalapa, CDMX",
        colonia="Santiago Acahualtepec",
        alcaldia="Iztapalapa",
        city="CDMX",
        lat=19.3350,
        lng=-99.0300,
        zone_type="low_income",
        zone_label="Tláhuac / Sur-Oriente",
        priority=2,
    ),
    Location(
        id="gam",
        address="Gran Canal 500, Casas Alemán, Gustavo A. Madero, CDMX",
        colonia="Casas Alemán",
        alcaldia="Gustavo A. Madero",
        city="CDMX",
        lat=19.4836,
        lng=-99.0921,
        zone_type="low_income",
        zone_label="GAM Norte",
        priority=2,
    ),
    Location(
        id="ecatepec",
        address="Av. Central 200, Ecatepec Centro, Ecatepec, Estado de México",
        colonia="Ecatepec Centro",
        alcaldia="Ecatepec",
        city="Ecatepec",
        lat=19.6012,
        lng=-99.0440,
        zone_type="low_income",
        zone_label="Ecatepec (Edo. Méx.)",
        priority=2,
    ),
    Location(
        id="satelite",
        address="Blvd. Manuel Ávila Camacho 1500, Cd. Satélite, Naucalpan, Edo. Méx.",
        colonia="Ciudad Satélite",
        alcaldia="Naucalpan",
        city="Naucalpan",
        lat=19.5040,
        lng=-99.2330,
        zone_type="low_income",
        zone_label="Satélite (Edo. Méx.)",
        priority=2,
    ),

    # ----- COMMERCIAL / CENTRO (3) -----
    Location(
        id="reforma",
        address="Av. Paseo de la Reforma 500, Juárez, Cuauhtémoc, CDMX",
        colonia="Juárez",
        alcaldia="Cuauhtémoc",
        city="CDMX",
        lat=19.4270,
        lng=-99.1616,
        zone_type="commercial",
        zone_label="Reforma (Oficinas)",
        priority=1,
    ),
    Location(
        id="centro",
        address="Av. 5 de Febrero 100, Centro Histórico, Cuauhtémoc, CDMX",
        colonia="Centro Histórico",
        alcaldia="Cuauhtémoc",
        city="CDMX",
        lat=19.4326,
        lng=-99.1332,
        zone_type="commercial",
        zone_label="Centro Histórico",
        priority=2,
    ),
    Location(
        id="chapultepec",
        address="Av. Chapultepec 200, Juárez, Cuauhtémoc, CDMX",
        colonia="Juárez",
        alcaldia="Cuauhtémoc",
        city="CDMX",
        lat=19.4235,
        lng=-99.1590,
        zone_type="commercial",
        zone_label="Chapultepec",
        priority=2,
    ),

    # ----- SECONDARY CITIES (2 — bonus) -----
    Location(
        id="guadalajara",
        address="Av. Vallarta 3000, Vallarta Poniente, Guadalajara, Jalisco",
        colonia="Vallarta Poniente",
        alcaldia="Guadalajara",
        city="Guadalajara",
        lat=20.6737,
        lng=-103.3823,
        zone_type="medium_high_income",
        zone_label="Guadalajara",
        priority=3,
    ),
    Location(
        id="monterrey",
        address="Av. Constitución 500, Centro, Monterrey, Nuevo León",
        colonia="Centro",
        alcaldia="Monterrey",
        city="Monterrey",
        lat=25.6714,
        lng=-100.3090,
        zone_type="medium_high_income",
        zone_label="Monterrey",
        priority=3,
    ),
]


# ============================================================
# Helper functions
# ============================================================

def get_locations_by_priority(max_priority: int = 2) -> list[Location]:
    """Get locations up to a given priority level."""
    return [loc for loc in LOCATIONS if loc.priority <= max_priority]


def get_locations_by_zone(zone_type: str) -> list[Location]:
    """Get locations for a specific zone type."""
    return [loc for loc in LOCATIONS if loc.zone_type == zone_type]


def get_locations_by_city(city: str) -> list[Location]:
    """Get locations for a specific city."""
    return [loc for loc in LOCATIONS if loc.city == city]


def get_quick_locations() -> list[Location]:
    """Get a minimal set of locations for quick demo (priority 1 only)."""
    return [loc for loc in LOCATIONS if loc.priority == 1]


def get_location_by_id(location_id: str) -> Location | None:
    """Get a single location by its ID."""
    for loc in LOCATIONS:
        if loc.id == location_id:
            return loc
    return None


# Quick access
QUICK_LOCATIONS = get_quick_locations()  # 6 locations for demo
FULL_LOCATIONS = get_locations_by_priority(2)  # 23 locations (no secondary cities)
ALL_LOCATIONS = LOCATIONS  # All 25 locations

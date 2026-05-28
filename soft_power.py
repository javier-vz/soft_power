import requests
import pandas as pd
import time

BASE_URL = "https://api.openalex.org/works"

SEARCH_TERMS = [
    "artificial intelligence cultural heritage",
    "machine learning cultural heritage",
    "deep learning cultural heritage",
    "computer vision cultural heritage",
    "knowledge graph cultural heritage",
    "large language model cultural heritage",
    "digital twin cultural heritage",
    "artificial intelligence archaeology",
    "machine learning archaeology",
    "computer vision museum",
    "machine learning intangible cultural heritage",
    "digital heritage artificial intelligence"
]

YEAR_FROM = "2015-01-01"
YEAR_TO = "2026-12-31"
COUNTRY_CODE = "CN"

MAX_RECORDS_PER_QUERY = 1000   # puedes subirlo luego
PER_PAGE = 100                 # OpenAlex permite hasta 100 por página


def reconstruct_abstract(abstract_inverted_index):
    """
    OpenAlex guarda muchos abstracts como índice invertido.
    Esta función reconstruye el texto.
    """
    if not abstract_inverted_index:
        return None

    words = []
    for word, positions in abstract_inverted_index.items():
        for pos in positions:
            words.append((pos, word))

    words = sorted(words, key=lambda x: x[0])
    return " ".join(word for _, word in words)


def extract_work(work, query):
    authorships = work.get("authorships", [])

    countries = set()
    institutions = set()
    authors = []

    for auth in authorships:
        author = auth.get("author", {})
        if author.get("display_name"):
            authors.append(author["display_name"])

        for inst in auth.get("institutions", []):
            if inst.get("country_code"):
                countries.add(inst["country_code"])
            if inst.get("display_name"):
                institutions.add(inst["display_name"])

    primary_location = work.get("primary_location") or {}
    source = primary_location.get("source") or {}

    topics = work.get("topics") or []
    concepts = work.get("concepts") or []

    return {
        "query": query,
        "openalex_id": work.get("id"),
        "doi": work.get("doi"),
        "title": work.get("title"),
        "publication_year": work.get("publication_year"),
        "publication_date": work.get("publication_date"),
        "type": work.get("type"),
        "cited_by_count": work.get("cited_by_count"),
        "is_oa": work.get("open_access", {}).get("is_oa"),
        "source": source.get("display_name"),
        "source_type": source.get("type"),
        "authors": "; ".join(authors),
        "institutions": "; ".join(sorted(institutions)),
        "countries": "; ".join(sorted(countries)),
        "topics": "; ".join([t.get("display_name", "") for t in topics[:5]]),
        "concepts": "; ".join([c.get("display_name", "") for c in concepts[:10]]),
        "abstract": reconstruct_abstract(work.get("abstract_inverted_index")),
    }


all_rows = []

for query in SEARCH_TERMS:
    print(f"\nDescargando query: {query}")

    cursor = "*"
    downloaded = 0

    while True:
        params = {
            "search": query,
            "filter": (
                f"authorships.institutions.country_code:{COUNTRY_CODE},"
                f"from_publication_date:{YEAR_FROM},"
                f"to_publication_date:{YEAR_TO}"
            ),
            "per-page": PER_PAGE,
            "cursor": cursor,
            "select": (
                "id,doi,title,publication_year,publication_date,type,"
                "cited_by_count,open_access,primary_location,authorships,"
                "topics,concepts,abstract_inverted_index"
            )
        }

        response = requests.get(BASE_URL, params=params, timeout=60)

        if response.status_code != 200:
            print("Error:", response.status_code, response.text[:500])
            break

        data = response.json()
        results = data.get("results", [])

        if not results:
            break

        for work in results:
            all_rows.append(extract_work(work, query))

        downloaded += len(results)
        print(f"  descargados: {downloaded}")

        cursor = data.get("meta", {}).get("next_cursor")

        if not cursor or downloaded >= MAX_RECORDS_PER_QUERY:
            break

        time.sleep(0.2)


df = pd.DataFrame(all_rows)

# Eliminar duplicados por OpenAlex ID
df = df.drop_duplicates(subset=["openalex_id"])

df.to_csv("openalex_china_ai_heritage.csv", index=False, encoding="utf-8-sig")
df.to_excel("openalex_china_ai_heritage.xlsx", index=False)

print("\nListo.")
print(f"Registros únicos: {len(df)}")
print("Archivos guardados:")
print("- openalex_china_ai_heritage.csv")
print("- openalex_china_ai_heritage.xlsx")
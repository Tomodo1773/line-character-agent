from pydantic import BaseModel, Field
from langchain_core.tools import tool
from dotenv import load_dotenv
from langchain_community.document_loaders import FireCrawlLoader
from langchain_core.documents.base import Document

load_dotenv()


class FirecrawlSearchInput(BaseModel):
    url: str = Field(description="web site url")


@tool("firecrawl-search-tool", args_schema=FirecrawlSearchInput)
def firecrawl_search(url: str) -> Document:
    """A tool for retrieving the content of a web page by specifying a URL. Useful when a user provides a URL."""
    loader = FireCrawlLoader(url=url, mode="scrape")
    docs = loader.load()
    return docs[0]


# Let's inspect some of the attributes associated with the tool.
# print(multiply.name)
# print(multiply.description)
# print(multiply.args)
# print(multiply.return_direct)

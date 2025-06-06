from dotenv import load_dotenv
from langchain_community.document_loaders import FireCrawlLoader
from langchain_community.retrievers import AzureAISearchRetriever
from langchain_core.documents.base import Document
from langchain_core.tools import tool
from pydantic import BaseModel, Field

load_dotenv()


class FirecrawlSearchInput(BaseModel):
    url: str = Field(description="web site url")


@tool("firecrawl-search-tool", args_schema=FirecrawlSearchInput)
def firecrawl_search(url: str) -> Document:
    """A tool for retrieving the content of a web page by specifying a URL. Useful when a user provides a URL."""
    loader = FireCrawlLoader(url=url, mode="scrape")
    docs = loader.load()
    return docs[0]


class AzureAISearchInput(BaseModel):
    query: str = Field(description="search query")


def azure_ai_search(query: str) -> str:
    """A tool for retrieving relevant entries from the user's personal diary stored in Azure AI Search.
    Useful for answering questions based on the user's past experiences and thoughts."""
    retriever = AzureAISearchRetriever(content_key="content", top_k=3, index_name="diary-vector")
    docs = retriever.invoke(query)
    documents = [{"diary_contents": [doc.page_content for doc in docs]}]
    return documents  # Return formatted diary entries as a string


if __name__ == "__main__":
    # firecrawl_search(url="https://www.example.com")
    docs = azure_ai_search("花火にいったのはいつだっけ？")
    print(docs)

from langchain_community.document_loaders.parsers import OpenAIWhisperParser
from langchain_core.documents.base import Blob
from dotenv import load_dotenv
import os
from langchain_core.documents import Document

load_dotenv()

api_key = os.getenv("OPENAI_API_KEY")


blob = Blob.from_path("sample.mp3")
whisper = OpenAIWhisperParser(api_key=api_key,response_format="json")

response = whisper.lazy_parse(blob)


for chunk in response:
    print(chunk.page_content)

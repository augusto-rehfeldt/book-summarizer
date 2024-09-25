import os
import tempfile
import xml.etree.ElementTree as ET
import subprocess
import ebooklib
import json
import logging
import PyPDF2
from bs4 import BeautifulSoup
from tqdm import tqdm
from typing import Set, Tuple, Optional

from cryptography.fernet import Fernet
from ebooklib import epub
from bs4 import BeautifulSoup
from tqdm import tqdm
from typing import Set, Tuple, Optional


def save_api_keys_to_file(keys):
    with open("api_keys.json", "w") as file:
        json.dump(keys, file)


def load_or_generate_key():
    key_file = "encryption_key.key"
    if os.path.exists(key_file):
        with open(key_file, "rb") as file:
            return Fernet(file.read())
    else:
        key = Fernet.generate_key()
        with open(key_file, "wb") as file:
            file.write(key)
        return key


def encrypt_api_key(api_key):
    return load_or_generate_key().encrypt(api_key.encode()).decode()


def decrypt_api_key(encrypted_key):
    return load_or_generate_key().decrypt(encrypted_key.encode()).decode()


def load_daily_requests():
    try:
        with open("daily_requests.json", "r") as f:
            daily_requests = json.load(f)
    except FileNotFoundError:
        daily_requests = {}
    finally:
        return daily_requests


def save_daily_requests(daily_requests):
    with open("daily_requests.json", "w") as f:
        json.dump(daily_requests, f)


# Helper functions for loading and saving processed/aborted books
def load_processed_books() -> Set[str]:
    try:
        with open("processed_books.json", "r") as f:
            return set(json.load(f))
    except FileNotFoundError:
        return set()


def choose_provider():
    # Load the configuration file
    config_path = os.path.join(os.path.dirname(__file__), "ai_providers_config.json")
    with open(config_path, "r") as config_file:
        config = json.load(config_file)

    # Display available providers
    print("Available AI providers:\n")
    for i, provider in enumerate(config["providers"], 1):
        print(f"{i}. {provider['name'].capitalize()}")

    # Get user choice for provider
    while True:
        try:
            choice = int(input("\nChoose a provider (enter the number): ")) - 1
            if 0 <= choice < len(config["providers"]):
                selected_provider = config["providers"][choice]
                break
            else:
                print("Invalid choice. Please try again.")
        except ValueError:
            print("Please enter a valid number.")

    # Display available models for the chosen provider
    print(f"\nAvailable models for {selected_provider['name'].capitalize()}:\n")
    for i, model in enumerate(selected_provider["models"], 1):
        print(f"{i}. {model['name']} (Max tokens: {model['max_tokens']})")

    # Get user choice for model
    while True:
        try:
            choice = int(input("\nChoose a model (enter the number): ")) - 1
            if 0 <= choice < len(selected_provider["models"]):
                selected_model = selected_provider["models"][choice]
                break
            else:
                print("Invalid choice. Please try again.")
        except ValueError:
            print("Please enter a valid number.")

    # Return the selected provider and model information
    return {
        "provider": selected_provider["name"],
        "model": selected_model["name"],
        "max_tokens": selected_model["max_tokens"],
    }


def seconds_to_time(seconds):
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    seconds = int(seconds % 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

def float_to_cost(cost_value):
    return f"${cost_value:.2f}"


def convert_to_readable_time(time_in_seconds: int) -> str:
    hours = int(time_in_seconds // 3600)
    minutes = int((time_in_seconds % 3600) // 60)
    seconds = int(time_in_seconds % 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def save_processed_books(processed_books: Set[str]) -> None:
    with open("processed_books.json", "w") as f:
        json.dump(list(processed_books), f)


def load_aborted_books() -> Set[str]:
    try:
        with open("aborted_books.json", "r") as f:
            return set(json.load(f))
    except FileNotFoundError:
        return set()


def save_aborted_books(aborted_books: Set[str]) -> None:
    with open("aborted_books.json", "w") as f:
        json.dump(list(aborted_books), f)


def convert_to_epub(book_file: str) -> str:
    """Convert .mobi and .azw3 files to .epub using calibre's ebook-convert."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Ensure the 'converted' directory exists
    converted_dir = os.path.join(script_dir, "converted")
    if not os.path.exists(converted_dir):
        os.makedirs(converted_dir)

    # Create a path for the converted epub file
    epub_file = os.path.join(converted_dir, os.path.basename(book_file).replace('.mobi', '.epub').replace('.azw3', '.epub'))
    
    # Run the conversion process
    subprocess.run(["ebook-convert", book_file, epub_file], check=True)

    return epub_file



def save_chunk_summary(
    book_dir: str, title: str, author: str, chunk_number: int, summary: str
) -> None:
    """Save individual chunk summaries."""
    summary_filename = f"{title} - {author} - Chunk {chunk_number}.txt"
    summary_path = os.path.join(book_dir, "chunk_summaries", summary_filename)
    os.makedirs(os.path.dirname(summary_path), exist_ok=True)

    with open(summary_path, "w", encoding="utf-8") as f:
        f.write(f"Title: {title}\n")
        f.write(f"Author: {author}\n")
        f.write(f"Chunk: {chunk_number}\n\n")
        f.write(summary)


def find_ocr_files(file_path):
    "from a book file path, search its parent directory to find the ocr file for that book"
    parent_dir = os.path.dirname(file_path)
    try:
        ocr_filename = [x for x in os.listdir(parent_dir) if x.endswith(".opf")][0]
    except IndexError:
        return None
    ocr_file = os.path.join(parent_dir, ocr_filename)
    if os.path.exists(ocr_file):
        return ocr_file
    else:
        return None


def parse_metadata(
    file_path: str,
) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    """Extract book metadata from an .opf file or directly from the ebook file."""
    ocr_file = find_ocr_files(file_path)
    if ocr_file:
        return parse_opf_metadata(ocr_file)
    else:
        if file_path.endswith(".epub"):
            return parse_epub_metadata(file_path)
        else:
            logging.error(f"Unsupported file format: {file_path}")
            return None, None, None, None


def parse_opf_metadata(
    opf_file: str,
) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    """Extract book metadata from an .opf file."""
    try:
        tree = ET.parse(opf_file)
        root = tree.getroot()
        title = root.find(".//{http://purl.org/dc/elements/1.1/}title").text
        author_elem = root.find(".//{http://purl.org/dc/elements/1.1/}creator")
        author = author_elem.text if author_elem is not None else ""
        series = ""
        series_index = ""
        for meta in root.findall(".//{http://www.idpf.org/2007/opf}meta"):
            if meta.get("name") == "calibre:series":
                series = meta.get("content")
            elif meta.get("name") == "calibre:series_index":
                series_index = meta.get("content")
        return title, author, series, series_index
    except ET.ParseError as e:
        logging.error(f"Error parsing metadata from {opf_file}: {e}")
        return None, None, None, None


def parse_epub_metadata(
    epub_file: str,
) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    """Extract book metadata directly from an .epub file."""
    try:
        book = epub.read_epub(epub_file)
        title = book.get_metadata("DC", "title")[0][0]
        author = book.get_metadata("DC", "creator")[0][0]
        series = None
        series_index = None
        for metadata in book.get_metadata("DC", "identifier"):
            if metadata[1] and metadata[1].get("scheme") == "calibre:series":
                series = metadata[0]
            elif metadata[1] and metadata[1].get("scheme") == "calibre:series_index":
                series_index = metadata[0]
        return title, author, series, series_index
    except Exception as e:
        logging.error(f"Error parsing metadata from {epub_file}: {e}")
        return None, None, None, None


def load_conversion_cache() -> dict[str, str]:
    "create a conversion cache and save as a json file pointing to epub files"
    "if the cache exists, return it directly"
    if os.path.exists("conversion_cache.json"):
        with open("conversion_cache.json", "r") as f:
            return json.load(f)
    else:
        return {}


def save_conversion_cache(conversion_cache: dict[str, str]) -> None:
    "save the conversion cache as a json file"
    with open("conversion_cache.json", "w") as f:
        json.dump(conversion_cache, f)


def read_epub(file_path: str) -> str:
    """Extract text from an epub, azw3, mobi, PDF, TXT, or HTML file."""

    conversion_cache = load_conversion_cache()

    if any(file_path.endswith(x) for x in [".azw3", ".mobi"]):
        if not file_path in conversion_cache or not os.path.exists(
            conversion_cache[file_path]
        ):
            conversion_cache[file_path] = convert_to_epub(file_path)
            save_conversion_cache(conversion_cache)

        book = epub.read_epub(conversion_cache[file_path])
        text = []

        for item in book.get_items():
            if item.get_type() == ebooklib.ITEM_DOCUMENT:
                soup = BeautifulSoup(item.get_content(), "html.parser")
                text.append(soup.get_text())

        return "\n".join(text)
    else:
        try:
            if file_path.endswith(".epub"):
                book = epub.read_epub(file_path)
                text = []

                for item in book.get_items():
                    if item.get_type() == ebooklib.ITEM_DOCUMENT:
                        soup = BeautifulSoup(item.get_content(), "html.parser")
                        text.append(soup.get_text())

                return "\n".join(text)
            elif file_path.endswith(".pdf"):
                # Use PyPDF2 to extract text
                with open(file_path, "rb") as pdf_file:
                    reader = PyPDF2.PdfFileReader(pdf_file)
                    text = []
                    for page_num in range(reader.numPages):
                        page = reader.getPage(page_num)
                        text.append(page.extract_text())
                    return "\n".join(text)
            elif file_path.endswith(".txt"):
                with open(file_path, "r", encoding="utf-8") as txt_file:
                    return txt_file.read()
            elif file_path.endswith(".html"):
                with open(file_path, "r", encoding="utf-8") as html_file:
                    soup = BeautifulSoup(html_file, "html.parser")
                    return soup.get_text()
            else:
                raise ValueError(f"Unsupported file type: {file_path}")
        except Exception as e:
            logging.error(f"Error reading content from {file_path}: {e}")
            return ""


def process_chunks(
    chunks, title, author, book_dir, manager, progress_callback=None
) -> Optional[str]:
    """Process and summarize chunks of the book content."""
    if len(chunks) == 1:
        logging.info("Summarizing entire book in one chunk...")
        summary = manager.create_final_summary(chunks[0], title, author)
        if summary:
            save_chunk_summary(book_dir, title, author, 1, summary)
            if progress_callback:
                progress_callback(1, 1)
            return summary
        else:
            logging.error(f"Failed to summarize {title} in one chunk")
            return None

    logging.info(f"Processing {len(chunks)} chunks...")
    chunk_summaries = []
    previous_summaries = ""
    error_flag = False

    total_steps = len(chunks) + 1  # Include final summary as a step

    # Processing each chunk
    for i, chunk in enumerate(tqdm(chunks, desc="Summarizing chunks")):
        logging.info(f"\nProcessing chunk {i+1}/{len(chunks)}")

        # Summarize the chunk, passing previous summaries
        summary = manager.summarize_chunk(chunk, previous_summaries)

        if summary:
            chunk_summaries.append(summary)
            save_chunk_summary(book_dir, title, author, i + 1, summary)

            # Append the previous summaries to the current one
            previous_summaries += "\n\n" + summary

            # Call the progress callback after the chunk is successfully summarized
            if progress_callback:
                progress_callback(i + 1, total_steps)
        else:
            error_flag = True
            logging.error(f"Failed to summarize chunk {i + 1} of {title}")
            break

    if not error_flag:
        final_summary = manager.create_final_summary(
            "\n\n".join(chunk_summaries), title, author
        )
        if final_summary:
            # Call the progress callback for the final summary
            if progress_callback:
                progress_callback(total_steps, total_steps)
            return final_summary
        else:
            logging.error(f"Failed to create final summary for {title}")
            return None
    else:
        logging.error(f"Aborting {title} due to errors during chunk summarization.")
        return None

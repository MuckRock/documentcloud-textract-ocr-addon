"""
This Add-On uses Amazon Textract
to perform OCR on documents within DocumentCloud
"""
import os
import re
import sys
import time
import requests
from PIL import Image
from documentcloud.addon import AddOn
from documentcloud.exceptions import APIError
from textractor import Textractor

class Textract(AddOn):
    """Class for Textract OCR Add-On"""
    def setup_credential_file(self):
        """Setup credential files for AWS CLI"""
        credentials = os.environ["TOKEN"]
        credentials_file_path = os.path.expanduser("~/.aws/credentials")
        # Create the ~/.aws directory if it doesn't exist
        aws_directory = os.path.dirname(credentials_file_path)
        if not os.path.exists(aws_directory):
            os.makedirs(aws_directory)
        with open(credentials_file_path, "w") as file:
            file.write(credentials)

    def download_file(self, url, filename):
        """Download an file from a URL and save it locally."""
        response = requests.get(url, timeout=20)
        with open(filename, "wb") as f:
            f.write(response.content)

    def convert_to_png(self, gif_filename, png_filename):
        """Convert a GIF image to PNG format."""
        gif_image = Image.open(gif_filename)
        gif_image.save(png_filename, "PNG")
    def validate(self):
        """Validate that we can run the OCR"""
        if self.get_document_count() is None:
            self.set_message(
                "It looks like no documents were selected. Search for some or "
                "select them and run again."
            )
            sys.exit(0)
        num_pages = 0
        for document in self.get_documents():
            num_pages += document.page_count
        try:
            self.charge_credits(num_pages)
        except ValueError:
            return False
        except APIError:
            return False
        return True

    def main(self):
        """The main add-on functionality goes here."""
        if not self.validate():
            self.set_message("You do not have sufficient AI credits to run this Add-On")
            sys.exit(0)
        self.setup_credential_file()
        extractor = Textractor(profile_name="default", region_name="us-east-1")
        to_tag = self.data.get("to_tag", False)
        for document in self.get_documents():
            s3_url = document.pdf_url
            pdf = self.download_file(s3_url, f"{document.slug}.pdf")

            document_info = extractor.start_document_text_detection(
                f"s3://s3.documentcloud.org/documents/{document.id}/{document.slug}.pdf", save_image=False
            )
            
            for page in document_info.pages:
                print(page.text)

            
            """pages = []
            for page in range(1, document.pages + 1):
                image_data = document.get_large_image(page)
                gif_filename = f"{document.id}-page{page}.gif"
                with open(gif_filename, 'wb') as f:
                    f.write(image_data)
                png_filename = f"{document.id}-page{page}.png"
                self.convert_to_png(gif_filename, png_filename)
                image = Image.open(png_filename)
                page_info = extractor.detect_document_text(file_source=image)

                # Create dc_page dictionary
                dc_page = {
                    "page_number": page-1,
                    "text": page_info.text,
                    "ocr": "textract",
                    "positions": []  # To store word positions
                }
                for word in page_info.words:
                    word_info = {
                        "text": word.text,
                        "x1": word.bbox.x,
                        "x2": (word.bbox.x + word.bbox.width),
                        "y1": word.bbox.y,
                        "y2": (word.bbox.y + word.bbox.height),
                        "confidence": word.confidence,
                    }
                    dc_page["positions"].append(word_info)
                print(dc_page)
                # Append dc_page to pages list
                pages.append(dc_page)
            """
            """ page_chunk_size = 100  # Set your desired chunk size
            for i in range(0, len(pages), page_chunk_size):
                chunk = pages[i : i + page_chunk_size]
                resp = self.client.patch(
                    f"documents/{document.id}/", json={"pages": chunk}
                )
                resp.raise_for_status()
                while True:
                    time.sleep(10)
                    if (
                        document.status == "success"
                    ):  # Break out of for loop if document status becomes success
                        break

            if to_tag:
                document.data["ocr_engine"] = "textract"
                document.save()
            """
if __name__ == "__main__":
    Textract().main()

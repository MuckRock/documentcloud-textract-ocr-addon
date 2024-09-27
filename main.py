"""
This Add-On uses Amazon Textract
to perform OCR on documents within DocumentCloud
"""
import os
import sys
import time
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
        with open(credentials_file_path, "w", encoding="utf-8") as file:
            file.write(credentials)

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
            document_info = extractor.start_document_text_detection(
                f"s3://s3.documentcloud.org/documents/{document.id}/{document.slug}.pdf", save_image=False
            )

            dc_pages = []
            for page in document_info.pages:
                dc_page = {
                    "page_number": page.page_num-1,
                    "text": page.text,
                    "ocr": "textract",
                    "positions": []
                }
                for word in page.words:
                    word_info = {
                        "text": word.text,
                        "x1": max(0, min(1, word.bbox.x)),
                        "x2": max(0, min(1, word.bbox.x + word.bbox.width)),
                        "y1": max(0, min(1, word.bbox.y)),
                        "y2": max(0, min(1, word.bbox.y + word.bbox.height)),
                        "confidence": word.confidence,
                    }
                    dc_page["positions"].append(word_info)
                dc_pages.append(dc_page)

            page_chunk_size = 50 # Set your desired chunk size
            for i in range(0, len(dc_pages), page_chunk_size):
                chunk = dc_pages[i : i + page_chunk_size]
                resp = self.client.patch(
                    f"documents/{document.id}/", json={"pages": chunk}
                )
                resp.raise_for_status()
                while True:
                    document_ref = self.client.documents.get(document.id)
                    time.sleep(10)
                    if (
                        document_ref.status == "success"
                    ):  # Break out of for loop if document status becomes success
                        break

            if to_tag:
                document.data["ocr_engine"] = "textract"
                document.save()
if __name__ == "__main__":
    Textract().main()

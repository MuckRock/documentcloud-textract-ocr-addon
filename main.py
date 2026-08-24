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

    # Page-push tuning constants
    PAGE_CHUNK_SIZE = 30
    PUSH_MAX_RETRIES = 5
    PUSH_RETRY_DELAY = 30

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

    def tag_document(self, document, max_retries=5, retry_delay=60):
        """Tags document with OCR engine"""
        retries = 0
        while retries < max_retries:
            try:
                print("Tagging document...")
                existing = document.data.get("ocr_engine", [])
                self.client.patch(
                    f"documents/{document.id}/data/ocr_engine/",
                    json={"values": ["textract"], "remove": existing},
                )
                print("Finished tagging document")
                break
            except APIError as exc:
                print(f"Error tagging document. {exc}. Retrying...")
                retries += 1
                time.sleep(retry_delay)
        else:
            print(f"Failed to tag document after {max_retries} attempts.")
            self.set_message(
                "Failed to set the OCR tag for this document. "
                "Email info@documentcloud.org to debug."
            )
            sys.exit(1)

    @staticmethod
    def _extract_positions(page):
        """Extract clamped word position boxes from a Textractor page"""
        positions = []
        for word in page.words:
            positions.append(
                {
                    "text": word.text,
                    "x1": max(0, min(1, word.bbox.x)),
                    "x2": max(0, min(1, word.bbox.x + word.bbox.width)),
                    "y1": max(0, min(1, word.bbox.y)),
                    "y2": max(0, min(1, word.bbox.y + word.bbox.height)),
                    "confidence": word.confidence,
                }
            )
        return positions

    def parse_pages(self, document_info):
        """Build a list of DC page dicts from a Textractor document result"""
        pages = []
        for page in document_info.pages:
            pages.append(
                {
                    "page_number": page.page_num - 1,
                    "text": page.text,
                    "ocr": "textract",
                    "positions": self._extract_positions(page),
                }
            )
        return pages

    def push_pages(self, document, pages):
        """PATCH page text/positions to the DC API in chunks, with retries"""
        for i in range(0, len(pages), self.PAGE_CHUNK_SIZE):
            chunk = pages[i : i + self.PAGE_CHUNK_SIZE]
            retries = 0
            while retries < self.PUSH_MAX_RETRIES:
                print(
                    f"Updating the page text "
                    f"(pages {i} to {i + self.PAGE_CHUNK_SIZE})"
                )
                try:
                    resp = self.client.patch(
                        f"documents/{document.id}/", json={"pages": chunk}
                    )
                    resp.raise_for_status()
                except APIError as exc:
                    # Retry only if the document is still processing
                    if "processing" in str(exc):
                        print(
                            "Document is still processing, retrying... "
                            f"(Attempt {retries + 1} of {self.PUSH_MAX_RETRIES})"
                        )
                        retries += 1
                        time.sleep(self.PUSH_RETRY_DELAY)
                        continue
                    print(f"Unexpected error: {exc}. Exiting retries.")
                    raise
                print("Completed updating the page text")
                break
            else:
                print(
                    f"Failed to update pages {i} to {i + self.PAGE_CHUNK_SIZE}"
                    f" after {self.PUSH_MAX_RETRIES} attempts."
                )
                break  # Exit loop if retries exceeded

    def main(self):
        """The main add-on functionality goes here."""
        self.client.session.headers.update({"User-Agent": "Textract OCR Add-On"})
        if not self.validate():
            self.set_message("You do not have sufficient AI credits to run this Add-On")
            sys.exit(0)
        self.setup_credential_file()
        extractor = Textractor(profile_name="default", region_name="us-east-1")
        to_tag = self.data.get("to_tag", False)
        for document in self.get_documents():
            document_info = extractor.start_document_text_detection(
                f"s3://s3.documentcloud.org/documents/{document.id}/{document.slug}.pdf",
                save_image=False,
            )
            pages = self.parse_pages(document_info)
            self.push_pages(document, pages)
            if to_tag:
                self.tag_document(document)


if __name__ == "__main__":
    Textract().main()

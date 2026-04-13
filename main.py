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
        self.client.session.headers.update({'User-Agent': 'Textract OCR Add-On'})
        if not self.validate():
            self.set_message("You do not have sufficient AI credits to run this Add-On")
            sys.exit(0)
        self.setup_credential_file()
        extractor = Textractor(profile_name="default", region_name="us-east-1")
        to_tag = self.data.get("to_tag", False)
        for document in self.get_documents():
            document_info = extractor.start_document_text_detection(
                f"s3://s3.documentcloud.org/documents/{document.id}/{document.slug}.pdf", 
                save_image=False
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

            page_chunk_size = 30
            max_retries = 5
            retry_delay = 30
            status_check_delay = 10

            for i in range(0, len(dc_pages), page_chunk_size):
                chunk = dc_pages[i : i + page_chunk_size]
                retries = 0

                while retries < max_retries:
                    print(f"Updating the page text (pages {i} to {i + page_chunk_size})")
                    try:
                        resp = self.client.patch(
                            f"documents/{document.id}/", json={"pages": chunk}
                        )
                        resp.raise_for_status()
                    except APIError as exc:
                        # Check the error message to determine if it's
                        # because the document is still processing
                        if "processing" in str(exc):  # Adjust based on actual error message format
                            print(
                                "Document is still processing, retrying... "
                                f"(Attempt {retries + 1} of {max_retries})"
                            )
                            retries += 1
                            time.sleep(retry_delay)
                            continue
                        # If it's another type of error, re-raise
                        print(f"Unexpected error: {exc}. Exiting retries.")
                        raise
                    print("Completed updating the page text")
                    break
                else:
                    print(
                        f"Failed to update pages {i} to {i + page_chunk_size}"
                        f" after {max_retries} attempts."
                    )
                    break  # Exit loop if retries exceeded

            # Tagging part
            if to_tag:
                retries = 0
                while retries < max_retries:
                    print("Checking document status before tagging...")
                    try:
                        document_ref = self.client.documents.get(document.id)
                        if document_ref.status == "success":
                            print("Tagging document...")
                            document.data["ocr_engine"] = "textract"
                            document.save()
                            print("Finished tagging document")
                            break
                        print(f"Document status is {document_ref.status}. Waiting for success...")
                        time.sleep(status_check_delay)
                    except APIError as exc:
                        print(f"Error checking document status: {exc}. Retrying...")
                        retries += 1
                        time.sleep(retry_delay)
                else:
                    print(f"Failed to tag document after {max_retries} attempts.")

if __name__ == "__main__":
    Textract().main()

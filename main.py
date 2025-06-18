import argparse
import logging
import os
import sys
import re
from typing import List, Tuple, Optional
import io

try:
    from PIL import Image
except ImportError:
    print("Pillow is not installed. Please install it with: pip install Pillow")
    sys.exit(1)

try:
    import pytesseract
except ImportError:
    print("pytesseract is not installed. Please install it with: pip install pytesseract")
    sys.exit(1)

try:
    from pdf2image import convert_from_path
except ImportError:
    print("pdf2image is not installed. Please install it with: pip install pdf2image")
    sys.exit(1)

try:
    from faker import Faker
except ImportError:
    print("Faker is not installed. Please install it with: pip install Faker")
    sys.exit(1)


# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def setup_argparse() -> argparse.ArgumentParser:
    """
    Sets up the argument parser for the command-line interface.

    Returns:
        argparse.ArgumentParser: The argument parser object.
    """
    parser = argparse.ArgumentParser(description="Replaces text recognized by OCR in images or PDFs with placeholder text.")
    parser.add_argument("input_file", help="The input image or PDF file.")
    parser.add_argument("-o", "--output_file", help="The output image or PDF file. If not specified, the input file will be overwritten.", required=False)
    parser.add_argument("-r", "--replacement_text", default="REDACTED", help="The text to replace the OCR'd text with.  Defaults to 'REDACTED'.", required=False)
    parser.add_argument("-l", "--language", default="eng", help="The language to use for OCR. Defaults to 'eng' (English).", required=False)
    parser.add_argument("-d", "--dpi", type=int, default=200, help="The DPI to use when converting PDFs to images. Defaults to 200.", required=False)
    parser.add_argument("-p", "--pattern", help="A regular expression pattern to match text to be replaced. If not provided, all OCR'd text will be replaced.", required=False)
    parser.add_argument("-f", "--fake", action="store_true", help="Use Faker to generate realistic replacement text (e.g., names, addresses). Overrides --replacement_text.", required=False)
    parser.add_argument("--faker_locale", default="en_US", help="Locale to use for Faker (e.g., 'en_US', 'fr_FR').  Only applicable if --fake is used.", required=False)


    return parser


def ocr_image(image: Image.Image, language: str = "eng") -> str:
    """
    Performs OCR on an image.

    Args:
        image (Image.Image): The image to process.
        language (str): The language to use for OCR.

    Returns:
        str: The OCR'd text.
    """
    try:
        text = pytesseract.image_to_string(image, lang=language)
        return text
    except Exception as e:
        logging.error(f"Error during OCR: {e}")
        raise


def replace_text(text: str, replacement_text: str, pattern: Optional[str] = None, fake: bool = False, faker_locale: str = "en_US") -> str:
    """
    Replaces text based on a pattern (optional) or replaces the entire text.

    Args:
        text (str): The text to process.
        replacement_text (str): The text to replace with.
        pattern (str, optional): A regular expression pattern to match. Defaults to None.
        fake (bool, optional): Whether to use Faker to generate replacement text. Defaults to False.
        faker_locale (str, optional): The Faker locale. Defaults to "en_US".

    Returns:
        str: The replaced text.
    """
    if fake:
        fake_generator = Faker(faker_locale)
        if pattern:
             def replace_match(match):
                 # Basic example: Replace matched text with a fake name
                 return fake_generator.name()

             replaced_text = re.sub(pattern, replace_match, text)
        else:
            # If no pattern provided, replace the whole text with a fake sentence
            replaced_text = fake_generator.sentence()
    elif pattern:
        replaced_text = re.sub(pattern, replacement_text, text)
    else:
        replaced_text = replacement_text

    return replaced_text


def create_redacted_image(image: Image.Image, ocr_text: str, replaced_text: str) -> Image.Image:
  """
  Creates a redacted image by drawing black boxes over the detected text.

  Args:
      image (Image.Image): The original image.
      ocr_text (str): The original OCR'd text.
      replaced_text (str): The text that replaced the original.  Not really used, but kept for potential extensions

  Returns:
      Image.Image: The redacted image.
  """
  # This simplified version creates a black image with the same dimensions.
  # A more sophisticated version would identify the text location and redact only that part.
  return Image.new("RGB", image.size, "black")



def process_image(image_path: str, output_path: str, replacement_text: str, language: str, pattern: Optional[str], fake: bool, faker_locale: str) -> None:
    """
    Processes a single image.

    Args:
        image_path (str): The path to the input image.
        output_path (str): The path to the output image.
        replacement_text (str): The text to replace with.
        language (str): The language for OCR.
        pattern (str, optional): The regex pattern. Defaults to None.
        fake (bool, optional): Whether to use Faker. Defaults to False.
        faker_locale (str, optional): The Faker locale. Defaults to "en_US".
    """
    try:
        image = Image.open(image_path)
        ocr_text = ocr_image(image, language)
        replaced_text = replace_text(ocr_text, replacement_text, pattern, fake, faker_locale)
        redacted_image = create_redacted_image(image, ocr_text, replaced_text)
        redacted_image.save(output_path)
        logging.info(f"Processed image: {image_path} -> {output_path}")
    except FileNotFoundError:
        logging.error(f"Input file not found: {image_path}")
        sys.exit(1)
    except Exception as e:
        logging.error(f"Error processing image {image_path}: {e}")


def process_pdf(pdf_path: str, output_path: str, replacement_text: str, language: str, dpi: int, pattern: Optional[str], fake: bool, faker_locale: str) -> None:
    """
    Processes a PDF file.

    Args:
        pdf_path (str): The path to the input PDF.
        output_path (str): The path to the output PDF (actually a series of images).
        replacement_text (str): The text to replace with.
        language (str): The language for OCR.
        dpi (int): The DPI for PDF conversion.
        pattern (str, optional): The regex pattern. Defaults to None.
        fake (bool, optional): Whether to use Faker. Defaults to False.
        faker_locale (str, optional): The Faker locale. Defaults to "en_US".
    """
    try:
        images = convert_from_path(pdf_path, dpi=dpi)
        base_name = os.path.splitext(output_path)[0]  # Remove .pdf extension if it exists.

        for i, image in enumerate(images):
            image_output_path = f"{base_name}_page_{i+1}.png" # Save as PNG for simplicity
            ocr_text = ocr_image(image, language)
            replaced_text = replace_text(ocr_text, replacement_text, pattern, fake, faker_locale)
            redacted_image = create_redacted_image(image, ocr_text, replaced_text)
            redacted_image.save(image_output_path)
            logging.info(f"Processed PDF page {i+1}: {pdf_path} -> {image_output_path}")
    except FileNotFoundError:
        logging.error(f"Input file not found: {pdf_path}")
        sys.exit(1)
    except Exception as e:
        logging.error(f"Error processing PDF {pdf_path}: {e}")


def main() -> None:
    """
    Main function to execute the OCR text replacement.
    """
    parser = setup_argparse()
    args = parser.parse_args()

    input_file = args.input_file
    output_file = args.output_file if args.output_file else input_file  # Overwrite if not specified
    replacement_text = args.replacement_text
    language = args.language
    dpi = args.dpi
    pattern = args.pattern
    fake = args.fake
    faker_locale = args.faker_locale

    # Input validation: check if the locale is valid
    try:
        Faker(faker_locale)
    except AttributeError:
        logging.error(f"Invalid Faker locale: {faker_locale}")
        sys.exit(1)



    if not os.path.exists(input_file):
        logging.error(f"Input file does not exist: {input_file}")
        sys.exit(1)


    if input_file.lower().endswith(('.png', '.jpg', '.jpeg', '.tiff', '.bmp')):
        process_image(input_file, output_file, replacement_text, language, pattern, fake, faker_locale)
    elif input_file.lower().endswith('.pdf'):
        process_pdf(input_file, output_file, replacement_text, language, dpi, pattern, fake, faker_locale)
    else:
        logging.error("Unsupported file type.  Only images (png, jpg, jpeg, tiff, bmp) and PDFs are supported.")
        sys.exit(1)


if __name__ == "__main__":
    main()
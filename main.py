import argparse
import logging
import os
import sys
import re
from typing import List, Tuple, Optional
import io

try:
    # I check each third-party import up front and stop with the install line.
    # A missing library would otherwise surface as a traceback halfway through
    # a run, after the user already pointed me at a real file. The cost is that
    # even --help needs all four libraries present.
    from PIL import Image, ImageDraw, ImageFont
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
    parser.add_argument("-o", "--output_file", help="The output image or PDF file. Required unless --in-place is given. An output path that resolves to the input file is refused.", required=False)
    parser.add_argument("--in-place", action="store_true", help="Overwrite the input file in place. Only applies when -o is not given.", required=False)
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


# Text-level helper kept for callers that only have a string. The image and
# PDF paths below do not use it; they work word by word in redact_image.
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


# I redact from word boxes, not from the flat OCR string, because the
# replacement has to land where the original word sat. The tesseract data
# dict is parallel lists, so index i has to be the same word in every column.
def _word_boxes(image: Image.Image, language: str):
    data = pytesseract.image_to_data(image, lang=language, output_type=pytesseract.Output.DICT)
    boxes = []
    texts = data.get("text", [])
    for i, word in enumerate(texts):
        # Tesseract pads the dict with empty rows for layout blocks. Those rows
        # carry no word to cover, and their coordinate fields are not reliable.
        if not word or not str(word).strip():
            continue
        try:
            # A row with unparseable coordinates is skipped, not guessed at. Drawing a
            # box at a made-up position would cover the wrong part of the page.
            boxes.append((str(word), int(data["left"][i]), int(data["top"][i]), int(data["width"][i]), int(data["height"][i])))
        except Exception:
            continue
    return boxes


def redact_image(image: Image.Image, replacement_text: str, pattern: Optional[str] = None, fake: bool = False, faker_locale: str = "en_US", language: str = "eng"):
    # I draw on an RGB copy. Palette and alpha images take rectangle fills and
    # saved output badly, and the caller's image stays untouched this way.
    result = image.convert("RGB").copy()
    draw = ImageDraw.Draw(result)
    try:
        font = ImageFont.load_default()
    except Exception:
        font = None
    fake_generator = Faker(faker_locale) if fake else None
    count = 0
    for word, x, y, w, h in _word_boxes(image, language):
        if pattern and not re.search(pattern, word):
            continue
        replacement = fake_generator.name() if fake_generator is not None else replacement_text
        # I blank the box first, then write over it. Drawing the replacement alone
        # would leave the tails of a longer original word visible. The replacement
        # is not shrunk to fit, so a long replacement can spill past the box.
        draw.rectangle([x, y, x + w, y + h], fill="white")
        if font is not None:
            draw.text((x, y), replacement, fill="black", font=font)
        else:
            draw.text((x, y), replacement, fill="black")
        count += 1
    return result, count


def create_redacted_image(image: Image.Image, ocr_text: str, replaced_text: str, pattern: Optional[str] = None, fake: bool = False, faker_locale: str = "en_US", replacement_text: Optional[str] = None, language: str = "eng") -> Image.Image:
    repl = replacement_text if replacement_text is not None else replaced_text
    result, _count = redact_image(image, repl, pattern=pattern, fake=fake, faker_locale=faker_locale, language=language)
    return result



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
        image.load()
        ocr_text = ocr_image(image, language)
        redacted_image, count = redact_image(image, replacement_text, pattern=pattern, fake=fake, faker_locale=faker_locale, language=language)
        # Zero replacements means the run did nothing the user asked for. I treat
        # that as a failure, not a success with an unchanged copy as the output.
        if count == 0:
            logging.error("No OCR text matched; nothing was replaced.")
            sys.exit(1)
        redacted_image.save(output_path)
        logging.info(f"Processed image: {image_path} -> {output_path} ({count} word(s) replaced)")
    except SystemExit:
        raise
    except FileNotFoundError:
        logging.error(f"Input file not found: {image_path}")
        sys.exit(1)
    except Exception as e:
        logging.error(f"Error processing image {image_path}: {e}")
        sys.exit(1)


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
        if not images:
            logging.error("No pages were read from the PDF; nothing was replaced.")
            sys.exit(1)
        redacted_images = []
        total = 0
        for i, image in enumerate(images):
            redacted_image, count = redact_image(image, replacement_text, pattern=pattern, fake=fake, faker_locale=faker_locale, language=language)
            redacted_images.append(redacted_image)
            total += count
            logging.info(f"Processed PDF page {i+1}: {count} word(s) replaced")
        if total == 0:
            logging.error("No OCR text matched; nothing was replaced.")
            sys.exit(1)
        # Pillow assembles a multi-page PDF from the first image plus append_images,
        # so page one is passed as the save target instead of joining the list.
        redacted_images[0].save(output_path, format="PDF", save_all=True, append_images=redacted_images[1:])
        logging.info(f"Processed PDF: {pdf_path} -> {output_path} ({total} word(s) replaced)")
    except SystemExit:
        raise
    except FileNotFoundError:
        logging.error(f"Input file not found: {pdf_path}")
        sys.exit(1)
    except Exception as e:
        logging.error(f"Error processing PDF {pdf_path}: {e}")
        sys.exit(1)


def main() -> None:
    """
    Main function to execute the OCR text replacement.
    """
    parser = setup_argparse()
    args = parser.parse_args()

    input_file = args.input_file
    if args.pattern:
        try:
            # I compile the pattern before any file work. A bad regex should cost the
            # user one second, not a full OCR pass that then throws away its result.
            re.compile(args.pattern)
        except re.error as e:
            logging.error(f"Invalid pattern: {e}")
            sys.exit(1)
    if args.output_file:
        # realpath on both sides, so a symlink or a .. path to the same file is
        # caught too. --in-place is the only sanctioned way to overwrite the input.
        if os.path.realpath(args.output_file) == os.path.realpath(input_file):
            logging.error("Output file resolves to the input file; refusing to overwrite it. Use --in-place to overwrite intentionally.")
            sys.exit(1)
        output_file = args.output_file
    elif getattr(args, "in_place", False):
        output_file = input_file
    else:
        logging.error("No output file given. Pass -o for an output file or --in-place to overwrite the input file.")
        sys.exit(1)
    replacement_text = args.replacement_text
    language = args.language
    dpi = args.dpi
    pattern = args.pattern
    fake = args.fake
    faker_locale = args.faker_locale

    # Input validation: check if the locale is valid
    # This runs even when --fake was not passed, so an invalid locale stops a
    # plain run too. I left that as is; the error names the locale either way.
    try:
        Faker(faker_locale)
    except AttributeError:
        logging.error(f"Invalid Faker locale: {faker_locale}")
        sys.exit(1)



    if not os.path.exists(input_file):
        logging.error(f"Input file does not exist: {input_file}")
        sys.exit(1)


    # Dispatch trusts the extension alone. A misnamed file reaches the wrong
    # processor and fails there, and I would rather name that than sniff bytes.
    if input_file.lower().endswith(('.png', '.jpg', '.jpeg', '.tiff', '.bmp')):
        process_image(input_file, output_file, replacement_text, language, pattern, fake, faker_locale)
    elif input_file.lower().endswith('.pdf'):
        process_pdf(input_file, output_file, replacement_text, language, dpi, pattern, fake, faker_locale)
    else:
        logging.error("Unsupported file type.  Only images (png, jpg, jpeg, tiff, bmp) and PDFs are supported.")
        sys.exit(1)


if __name__ == "__main__":
    main()
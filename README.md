# dso-ocr-text-replacer
Replaces text recognized by OCR (Optical Character Recognition) in images or PDFs with placeholder text or other configurable values. - Focused on Tools for sanitizing and obfuscating sensitive data within text files and structured data formats

## Install
`git clone https://github.com/ShadowGuardAI/dso-ocr-text-replacer`

## Usage
`./dso-ocr-text-replacer [params]`

## Parameters
- `-h`: Show help message and exit
- `-o`: The output image or PDF file. If not specified, the input file will be overwritten.
- `-r`: The text to replace the OCR
- `-l`: The language to use for OCR. Defaults to 
- `-d`: The DPI to use when converting PDFs to images. Defaults to 200.
- `-p`: A regular expression pattern to match text to be replaced. If not provided, all OCR
- `-f`: No description provided
- `--faker_locale`: Locale to use for Faker (e.g., 

## License
Copyright (c) ShadowGuardAI

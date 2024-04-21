import logging
import os
import requests
import sys
import urllib.request
from bs4 import BeautifulSoup

format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
logging.basicConfig(format=format, stream=sys.stdout, level=logging.DEBUG)

def get_url_page(url: str) -> bytes:
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as response:
            return response.read()
    except:
        logging.exception(f"Error reading the url {url}")


def get_files(html: bytes) -> list:
    page = BeautifulSoup(html, features="html.parser")
    files: list[str] = []
    for a in page.find_all('a', href=True):
        if a["href"].endswith("csv"):
            files.append(a['href'])
    return files


def download_file(url: str, filename: str, output_folder: str) -> None:
    try:
        req = requests.get(os.path.join(url, filename), verify=False, timeout=300)
        with open(os.path.join(output_folder, filename), "wb") as f:
            f.write(req.content)
        logging.info(f"File {filename} downloaded in the folder {output_folder}")
    except:
        logging.exception("Request error!")


if __name__ == "__main__":

    OMOP_URL = "https://physionet.org/files/mimic-iv-demo-omop/0.9/1_omop_data_csv/"
    my_html = get_url_page(url=OMOP_URL)
    files = get_files(html=my_html)

    for file in files:
        download_file(OMOP_URL, filename=file, output_folder="data")

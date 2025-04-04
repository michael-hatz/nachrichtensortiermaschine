
from bs4 import BeautifulSoup
import trafilatura
import pandas as pd
import markdown

def load_killfile():
    """Load the killfile.txt into a list of phrases."""
    killfile_path = "/home/michael/Nextcloud/nsm/docker-github/src/killfile.txt"
    with open(killfile_path, "r", encoding="utf-8") as file:
        # Split the file into paragraphs (phrases)
        return [paragraph.strip() for paragraph in file.read().split("\n\n") if paragraph.strip()]


def filter_killfile(content, killfile):
    """
    Remove all phrases in the killfile from the content while preserving HTML formatting.
    Handles phrases with or without HTML formatting in the content.
    """
    # Parse the HTML content
    soup = BeautifulSoup(content, "html.parser")

    # Iterate over all text nodes in the HTML
    for text_node in soup.find_all(string=True):
        # Normalize the text node
        text = text_node.strip()
        for phrase in killfile:
            # Normalize the killfile phrase
            normalized_phrase = phrase.strip()
            # Remove the killfile phrase from the text node
            if normalized_phrase in text:
                text = text.replace(normalized_phrase, "")
        # Update the text node with the filtered text
        text_node.replace_with(text)

    # Return the modified HTML as a string
    return str(soup)

text_trafilatura = trafilatura.fetch_url("https://taz.de/Tunesien-raeumt-Fluechtlingscamps/!6080850/")
#new_data = pd.DataFrame({'URL': [entry.link]})
#seen_urls = pd.concat([seen_urls, new_data], ignore_index=True)
#print("new_data:" , new_data)                
#entry.content = [{'type': 'text/plain', 'language': None, 'base': '', 'value': 'Test'}]
#if entry.content is not None and not isinstance(entry.content, Exception):
# Code to execute if text_trafilatura is not None and not an error
h = trafilatura.extract(text_trafilatura, include_comments=False, include_links=True, include_formatting=True)              
if h is not None:
    text = markdown.markdown(h)
    print(text)
    killfile = load_killfile()
    x = filter_killfile(text, killfile)
    print(x)
    
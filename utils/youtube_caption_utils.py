"""
YouTube Caption Processing Script

This script fetches captions from a YouTube video given its URL, and processes
them into:
- A dictionary of sentences,
- A dictionary of word lists (with contractions expanded),
- A flat list of words (with contractions expanded).

Functions:
    - extract_video_id: Extracts video ID from YouTube URL.
    - expand_contractions: Expands common English contractions in a list of words.
    - get_youtube_captions_as_dict: Returns captions as {minute: sentence}.
    - get_youtube_captions_as_dict_list: Returns captions as {minute: list of words}.
    - get_youtube_captions_as_words: Returns captions as a flat list of words.

Dependencies:
    - youtube_transcript_api
"""

from typing import List, Dict, Optional
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import NoTranscriptFound, VideoUnavailable
from urllib.parse import urlparse, parse_qs


def extract_video_id(youtube_url: str) -> Optional[str]:
    """
    Extracts the video ID from a YouTube URL.

    Args:
        youtube_url (str): Full YouTube URL.

    Returns:
        Optional[str]: The extracted video ID, or None if extraction fails.
    """
    try:
        parsed_url = urlparse(youtube_url)

        if parsed_url.netloc == "youtu.be":
            return parsed_url.path.lstrip("/")
        
        if "youtube.com" in parsed_url.netloc:
            query_params = parse_qs(parsed_url.query)
            return query_params.get("v", [None])[0]

        print("Invalid YouTube URL format.")
        return None

    except Exception as e:
        print(f"An error occurred: {e}")
        return None


def expand_contractions(word_list: List[str]) -> List[str]:
    """
    Expands common English contractions in a list of words.

    Args:
        word_list (List[str]): List of words possibly containing contractions.

    Returns:
        List[str]: A new list with contractions expanded into separate words.
    """
    contractions = {
        "it's": "it is",
        "you're": "you are",
        "i'm": "i am",
        "don't": "do not",
        "can't": "cannot",
        "they're": "they are",
        "i'll": "i will",
        "you'll": "you will",
        "we'll": "we will",
        "they'll": "they will",
        "i'd": "i would",
        "you'd": "you would",
        "he'd": "he would",
        "she'd": "she would",
        "we'd": "we would",
        "they'd": "they would",
        "it'll": "it will",
        "won't": "will not",
        "isn't": "is not",
        "aren't": "are not",
        "wasn't": "was not",
        "weren't": "were not",
        "hasn't": "has not",
        "haven't": "have not",
        "hadn't": "had not",
        "doesn't": "does not",
        "didn't": "did not",
        "wouldn't": "would not",
        "shouldn't": "should not",
        "mightn't": "might not",
        "mustn't": "must not",
        "let's": "let us",
        "who's": "who is",
        "what's": "what is",
        "where's": "where is",
        "when's": "when is",
        "why's": "why is",
        "how's": "how is",
        "couldn't": "could not",
        "shan't": "shall not",
        "o'clock": "of the clock",
        "she's": "she is",
        "he's": "he is",
        "that's": "that is",
        "there's": "there is",
        "here's": "here is",
        "we're": "we are",
    }

    expanded_list: List[str] = []
    for word in word_list:
        word_lower = word.lower()
        if word_lower in contractions:
            expanded_list.extend(contractions[word_lower].split())
        else:
            expanded_list.append(word)

    return expanded_list


def get_youtube_captions_as_dict(video_id: str) -> Dict[float, str]:
    """
    Fetches captions and returns a dictionary mapping minutes to full caption sentences.

    Args:
        video_id (str): YouTube video ID.

    Returns:
        Dict[float, str]: {minute: caption sentence}.
    """
    try:
        transcript = YouTubeTranscriptApi.get_transcript(video_id)
        captions_dict: Dict[float, str] = {}

        for entry in transcript:
            time_in_minutes = round(entry['start'] / 60, 2)
            captions_dict[time_in_minutes] = entry['text']

        return captions_dict

    except NoTranscriptFound:
        print("No transcript available for this video.")
        return {}
    except VideoUnavailable:
        print("Video is unavailable.")
        return {}
    except Exception as e:
        print(f"An error occurred: {e}")
        return {}


def get_youtube_captions_as_dict_list(video_id: str) -> Dict[float, List[str]]:
    """
    Fetches captions and returns a dictionary mapping minutes to lists of words.

    Args:
        video_id (str): YouTube video ID.

    Returns:
        Dict[float, List[str]]: {minute: list of words}.
    """
    try:
        transcript = YouTubeTranscriptApi.get_transcript(video_id)
        captions_dict: Dict[float, List[str]] = {}

        for entry in transcript:
            time_in_minutes = round(entry['start'] / 60, 2)
            words = entry['text'].split()

            if time_in_minutes in captions_dict:
                captions_dict[time_in_minutes].extend(words)
            else:
                captions_dict[time_in_minutes] = words

        return captions_dict

    except NoTranscriptFound:
        print("No transcript available for this video.")
        return {}
    except VideoUnavailable:
        print("Video is unavailable.")
        return {}
    except Exception as e:
        print(f"An error occurred: {e}")
        return {}


def get_youtube_captions_as_words(video_id: str) -> List[str]:
    """
    Fetches captions and returns a flat list of all words from the video.

    Args:
        video_id (str): YouTube video ID.

    Returns:
        List[str]: List of words from all captions.
    """
    try:
        transcript = YouTubeTranscriptApi.get_transcript(video_id)
        words: List[str] = []

        for entry in transcript:
            words.extend(entry['text'].split())

        return words

    except NoTranscriptFound:
        print("No transcript available for this video.")
        return []
    except VideoUnavailable:
        print("Video is unavailable.")
        return []
    except Exception as e:
        print(f"An error occurred: {e}")
        return []

def get_youtube_captions_with_timing(video_id: str) -> List[Dict]:
    """
    Returns caption entries with start time, duration, and text.

    Example:
    [
        {"start": 2.1, "duration": 4.3, "text": "Hello world"},
        ...
    ]
    """
    try:
        transcript = YouTubeTranscriptApi.get_transcript(video_id)
        return transcript
    except Exception as e:
        print(f"Error getting transcript: {e}")
        return []

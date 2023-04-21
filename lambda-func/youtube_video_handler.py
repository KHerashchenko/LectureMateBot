from youtube_transcript_api import YouTubeTranscriptApi
from urllib.parse import urlparse, parse_qs, urlencode
from urllib.request import urlopen
import simplejson


def retrieve_metadata(url):
    params = {"format": "json", "url": url}
    url = "https://www.youtube.com/oembed"
    query_string = urlencode(params)
    query_url = url + "?" + query_string
    json_response = simplejson.load(urlopen(query_url))

    title = json_response['title']
    author = json_response['author_name']

    return title, author


def generate_transcript(url):
    parsed_url = urlparse(url)
    video_id = parse_qs(parsed_url.query)['v'][0]
    transcript_result = YouTubeTranscriptApi.get_transcript(video_id)
    full_transcript = ""
    filename = f'/tmp/transcript_{video_id}.txt'
    with open(filename, 'w') as f:
        for text in transcript_result:
            t = text["text"]
            full_transcript += t + " "
            f.write(t)

    return full_transcript, len(full_transcript.split()), filename
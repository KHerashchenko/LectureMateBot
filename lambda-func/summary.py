import openai
import math
from pyrate_limiter import RequestRate, Duration, Limiter
import markdown
import tiktoken
import pdfkit

tokenizer = tiktoken.get_encoding(
    "cl100k_base"
)

rate_limits = (RequestRate(3, Duration.MINUTE),) 
SUMMARY_RATIO = 0.4
MAX_AVAILABLE_TOKEN_SIZE = 3600


# Create the rate limiter
# Pyrate Limiter instance
limiter = Limiter(*rate_limits)

@limiter.ratelimit('gpt3.5', delay=True)
def get_completion(prompt, model="gpt-3.5-turbo"): # Andrew mentioned that the prompt/ completion paradigm is preferable for this class
    messages = [{"role": "user", "content": prompt}]
    response = openai.ChatCompletion.create(
        model=model,
        messages=messages,
        temperature=0, # this is the degree of randomness of the model's output
    )
    return response.choices[0].message["content"]

def markdown_to_pdf(markdown_string, output_file_path):
    # Convert to HTML
    html_text = markdown.markdown(markdown_string)

    config = pdfkit.configuration(wkhtmltopdf="/opt/bin/wkhtmltopdf")
    pdfkit.from_string(html_text, output_file_path, configuration=config)

def create_summary_prompt(wc, transcript_part):
    prompt = f"""
    Your task is to summarize a transcription of a video.
    The transcription of the video is in between the squared brackets.
    The summary should be maximum {wc} words.

    [{transcript_part}]
    
    Summary:
    """
    return prompt

def create_markdown_prompt(text, create_title):
    prompt = f"""
    Your task to format the text between the square brackets with markdown.
    Make it well structure use diffent type of titles, highlight important key words,
    if it make sens create bulletpoints.
    {"Do not create level 1 heading." if not create_title else ""}

    [{text}]
    
    Markdown formatted text:
    """
    return prompt


def generate_summary_pdf(transcript_text, video_id):
    tokenized_text = tokenizer.encode(transcript_text)
    token_count = len(tokenized_text)
    max_part_len = math.floor(MAX_AVAILABLE_TOKEN_SIZE / (1 + SUMMARY_RATIO))
    part_len = min(token_count, max_part_len)

    print('part', part_len)

    slices = []
    iter_num = math.ceil(token_count / max_part_len)
    for i in range(iter_num):
        slices.append(slice(i*part_len, (i+1)*part_len))
    
    results = []
    for i, slice_i in enumerate(slices):
        print('FOR', i)
        wc = round(len(tokenized_text[slice_i]) * SUMMARY_RATIO)
        
        text = tokenized_text[slice_i]
        prompt = create_summary_prompt(wc, tokenizer.decode(text))
        response = get_completion(prompt)

        prompt = create_markdown_prompt(response, i == 0)
        response = get_completion(prompt)

        print(response)
        
        results.append(response)

    results_string = "\n\n".join(results)
    filename = f'/tmp/summary_{video_id}.pdf'
    markdown_to_pdf(results_string, filename)

    return filename
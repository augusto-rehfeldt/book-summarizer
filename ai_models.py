import logging
import requests
import subprocess
import json
import time
import getpass
import ollama
import anthropic
import g4f

from g4f.client import Client
from google import genai
from google.genai import types
from huggingface_hub import InferenceClient
from openai import OpenAI
from mistralai import Mistral


class BaseManager:
    def __init__(
        self,
        model: str,
        max_tokens: int,
        retries: int = 5,
        temperature: float = 0.2,
        system_message: str = "You are an expert literary analyst. Your task is to provide a detailed summary of the given text chunk, focusing on plot developments, character arcs, and key events. Ensure continuity with previous summaries if provided. Your summary should be comprehensive yet concise. Only provide the summary.",
    ):
        self.model = model
        self.max_tokens = max_tokens
        self.retries = retries
        self.temperature = temperature
        self.system_message = system_message
        self.last_request_time = 0
        self.min_request_interval = 1.0  # seconds

    def _wait_for_rate_limit(self):
        """Ensure minimum time between API requests"""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        if time_since_last < self.min_request_interval:
            time.sleep(self.min_request_interval - time_since_last)
        self.last_request_time = time.time()

    def summarize_chunk(self, content: str, previous_summaries: str) -> str:
        prompt = f"""
        Previous summaries: {previous_summaries if previous_summaries else 'None'}

        Please summarize the following content, maintaining continuity with previous summaries:

        {content}

        Make it around 300 words. DO NOT EXCEED THIS.

        Provide a coherent narrative that captures the essence of this part of the story.
        """
        for attempt in range(self.retries):
            try:
                response = self._generate_response(prompt)
            except Exception as e:
                logging.error(
                    f"Error during summarization (attempt {attempt + 1}): {e}"
                )
                if attempt < self.retries - 1:
                    time.sleep(2**attempt)  # Exponential backoff
                else:
                    logging.warning("Max retries reached. Skipping this chunk.")
                    return ""
            else:
                response_length = len(response.split(" "))
                if response_length > 800:  # around 1000 tokens
                    logging.error(
                        f"Error during summarization (attempt {attempt + 1}): summary is too long."
                    )
                    continue
                elif response_length < 100:
                    logging.error(
                        f"Error during summarization (attempt {attempt + 1}): summary is too short."
                    )
                    continue
                return response

    def create_final_summary(self, summaries: str, title: str, author: str) -> str:
        prompt = f"""
        Based on the following chunk summaries, create a comprehensive summary of the entire book:

        {summaries}

        Your summary should provide an engaging overview of the plot from beginning to end.

        Book title: {title}
        Author: {author}
        """
        for attempt in range(self.retries):
            try:
                response = self._generate_response(prompt)
            except Exception as e:
                logging.error(
                    f"Error during final summarization (attempt {attempt + 1}): {e}"
                )
                if attempt < self.retries - 1:
                    time.sleep(2**attempt)
                else:
                    logging.warning(
                        "Max retries reached. Skipping final summary creation."
                    )
                    return ""
            else:
                if len(response) < 200:
                    logging.error(
                        f"Error during summarization (attempt {attempt + 1}): final summary is too short."
                    )
                    continue
                return response

class G4FManager(BaseManager):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.client = Client()
        self.min_request_interval = 2.0  # Increased delay for G4F rate limiting

    def _generate_response(self, prompt: str) -> str:
        self._wait_for_rate_limit()
        
        messages = [
            {"role": "system", "content": self.system_message},
            {"role": "user", "content": prompt}
        ]
        
        for attempt in range(self.retries):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens
                )
                
                if not response.choices or not response.choices[0].message.content:
                    raise ValueError(f"Unexpected response format: {response}")
                
                return response.choices[0].message.content

            except Exception as e:
                logging.error(f"G4F API request failed (attempt {attempt + 1}/{self.retries}): {e}")
                if attempt < self.retries - 1:
                    time.sleep(2 ** attempt)  # Exponential backoff
                continue
                
        logging.error("Failed to get valid response from G4F after all retries")
        return ""

class OpenAIBaseManager(BaseManager):
    def __init__(self, api_key: str, base_url: str = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.client = OpenAI(api_key=api_key, base_url=base_url)

    def _generate_response(self, prompt: str) -> str:
        self._wait_for_rate_limit()
        messages = [
            {"role": "system", "content": self.system_message},
            {"role": "user", "content": prompt},
        ]
        completion = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
        )
        return completion.choices[0].message.content


class OpenAIManager(OpenAIBaseManager):
    def __init__(self, api_key: str, *args, **kwargs):
        super().__init__(api_key=api_key, *args, **kwargs)


class LMStudioManager(OpenAIBaseManager):
    def __init__(self, *args, **kwargs):
        super().__init__(api_key="", base_url="http://127.0.0.1:1234/v1", *args, **kwargs)


class OpenRouterManager(OpenAIBaseManager):
    def __init__(self, api_key: str, *args, **kwargs):
        super().__init__(api_key=api_key, base_url="https://openrouter.ai/api/v1", *args, **kwargs)


class GLHFManager(OpenAIBaseManager):
    def __init__(self, api_key: str, *args, **kwargs):
        super().__init__(api_key=api_key, base_url="https://glhf.chat/api/openai/v1", *args, **kwargs)


class AlibabaManager(OpenAIBaseManager):
    def __init__(self, api_key: str, *args, **kwargs):
        super().__init__(api_key=api_key, base_url="https://dashscope.aliyuncs.com/compatible-mode/v1", *args, **kwargs)


class DeepInfraManager(OpenAIBaseManager):
    def __init__(self, api_key: str, *args, **kwargs):
        super().__init__(api_key=api_key, base_url="https://api.deepinfra.com/v1/openai", *args, **kwargs)


class MistralManager(BaseManager):
    def __init__(self, api_key: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.client = Mistral(api_key=api_key)

    def _generate_response(self, prompt: str) -> str:
        self._wait_for_rate_limit()
        messages = [
            {"role": "system", "content": self.system_message},
            {"role": "user", "content": prompt},
        ]
        completion = self.client.chat.complete(
            model=self.model,
            temperature=self.temperature,
            messages=messages,
        )
        return completion.choices[0].message.content


class ArliAiManager(BaseManager):
    def __init__(self, api_key: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.api_key = api_key

    def _generate_response(self, prompt: str) -> str:
        self._wait_for_rate_limit()
        payload = json.dumps({
            "model": self.model,
            "messages": [
                {"role": "system", "content": self.system_message},
                {"role": "user", "content": prompt}
            ],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": False
        })
        
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f"Bearer {self.api_key}"
        }

        response = requests.request("POST", "https://api.arliai.com/v1/chat/completions", headers=headers, data=payload)
        
        return response.json()["choices"][0]["message"]["content"]


class OllamaManager(BaseManager):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.start_ollama()

    def start_ollama(self):
        username = getpass.getuser()
        subprocess.run(
            [f"C:\\Users\\{username}\\AppData\\Local\\Programs\\Ollama\\ollama app.exe"]
        )

    def _generate_response(self, prompt: str) -> str:
        self._wait_for_rate_limit()
        stream = ollama.chat(
            model=self.model,
            messages=[
                {"role": "system", "content": self.system_message},
                {"role": "user", "content": prompt},
            ],
            stream=True,
            options={"temperature": self.temperature},
        )

        response = ""
        latest_50 = ""  # track the latest 50 characters to check for repeats

        for i, chunk in enumerate(stream):
            response += chunk["message"]["content"]
            latest_50 += chunk["message"]["content"]
            if i >= 50:
                latest_50 = latest_50[-50:]
                if response.count(latest_50) > 1:
                    # parse response to eliminate repeats
                    response = " ".join(response.split(latest_50)[:-1])
                    return response

        return response


class GeminiManager(BaseManager):
    def __init__(self, api_key: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.client = genai.Client(api_key=api_key)
        

    def _generate_response(self, prompt: str) -> str:
        self._wait_for_rate_limit()

        safety_settings = [
            types.SafetySetting(
                category="HARM_CATEGORY_HATE_SPEECH",
                threshold="BLOCK_NONE",
            ),
            types.SafetySetting(
                category="HARM_CATEGORY_HARASSMENT",
                threshold="BLOCK_NONE",
            ),
            types.SafetySetting(
                category="HARM_CATEGORY_SEXUALLY_EXPLICIT",
                threshold="BLOCK_NONE",
            ),
            types.SafetySetting(
                category="HARM_CATEGORY_DANGEROUS_CONTENT",
                threshold="BLOCK_NONE",
            ),
            types.SafetySetting(
                category="HARM_CATEGORY_CIVIC_INTEGRITY",
                threshold="BLOCK_NONE",
            ),
        ]

        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=self.temperature,
                safety_settings=safety_settings,
            ),
        )
        return response.text


class HuggingFaceManager(BaseManager):
    def __init__(self, api_key: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.client = InferenceClient(api_key=api_key)

    def _generate_response(self, prompt: str) -> str:
        self._wait_for_rate_limit()
        messages = [
            {"role": "system", "content": self.system_message},
            {"role": "user", "content": prompt},
        ]
        completion = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
        )
        return completion.choices[0].message.content


class AnthropicManager(BaseManager):
    def __init__(self, api_key: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.client = anthropic.Anthropic(api_key=api_key)

    def _generate_response(self, prompt: str) -> str:
        self._wait_for_rate_limit()
        completion = self.client.messages.create(
            model=self.model,
            temperature=self.temperature,
            system=self.system_message,
            messages=[{"role": "user", "content": prompt}],
        )
        return completion.content

# Import required modules
import re
import time
from copy import copy
from os import environ
from rich import print

import openai

from .base_translator import Base

# A mapping to get the right environment variable for different prompt types
PROMPT_ENV_MAP = {
    "user": "BBM_CHATGPTAPI_USER_MSG_TEMPLATE",
    "system": "BBM_CHATGPTAPI_SYS_MSG",
}


# The main class that handles translation using the OpenAI API
class ChatGPTAPI(Base):
    # Default prompt that the model uses to translate text
    DEFAULT_PROMPT = "Please help me to translate,`{text}` to {language}, please return only translated content not include the origin text"

    # The initializer sets up the instance with necessary parameters like the key, language, and various optional parameters
    def __init__(
            self,
            key,  # API key for OpenAI
            language,  # target language for translation
            api_base=None,  # base URL for API calls
            prompt_template=None,  # template for the prompt used in translation
            prompt_sys_msg=None,  # system message used in chat completion
            **kwargs,  # other keyword arguments
    ) -> None:
        super().__init__(key, language)  # call the initializer of the base class
        self.key_len = len(key.split(","))  # calculate the length of the key

        # Set the API base URL if provided
        if api_base:
            openai.api_base = api_base
        # Set the prompt template using the environment variable or the default prompt
        self.prompt_template = (
                prompt_template
                or environ.get(PROMPT_ENV_MAP["user"])
                or self.DEFAULT_PROMPT
        )
        # Set the system message for the chat completion
        self.prompt_sys_msg = (
                prompt_sys_msg
                or environ.get(
            "OPENAI_API_SYS_MSG",
        )  # XXX: for backward compatibility, deprecate soon
                or environ.get(PROMPT_ENV_MAP["system"])
                or ""
        )
        # Get the system content from the environment variable
        self.system_content = environ.get("OPENAI_API_SYS_MSG") or ""
        # Initialize the deployment ID to None
        self.deployment_id = None

    # This method rotates the API key
    def rotate_key(self):
        openai.api_key = next(self.keys)

    # This method creates a chat completion using the OpenAI API
    def create_chat_completion(self, text):
        # Formulate the content for the user message
        content = self.prompt_template.format(
            text=text, language=self.language, crlf="\n"
        )
        # Get the system content for the chat completion
        sys_content = self.system_content or self.prompt_sys_msg.format(crlf="\n")
        # Create a list of messages for the chat completion
        messages = [
            {"role": "system", "content": sys_content},
            {"role": "user", "content": content},
        ]

        # If a deployment ID is set, use it to create the chat completion
        if self.deployment_id:
            return openai.ChatCompletion.create(
                engine=self.deployment_id,
                messages=messages,
            )
        return openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=messages,
        )

    # This method returns a translation of a text
    def get_translation(self, text):
        self.rotate_key()
        completion = {}
        try:
            completion = self.create_chat_completion(text)
        except Exception:
            if (
                "choices" not in completion
                or not isinstance(completion["choices"], list)
                or len(completion["choices"]) == 0
            ):
                raise
            if completion["choices"][0]["finish_reason"] != "length":
                raise
        # The method handles cases where the text is too long to be completely translated
        choice = completion["choices"][0]

        t_text = choice.get("message").get("content", "").encode("utf8").decode()

        # If the text was too long to be fully translated
        if choice["finish_reason"] == "length":
            with open("log/long_text.txt", "a") as f:
                print(
                    f"""==================================================
        The total token is too long and cannot be completely translated\n
        {text}
        """,
                    file=f,
                )

        return t_text

        # This method tries to get a translation for a given text

    def translate(self, text, needprint=True):
        start_time = time.time()
        if needprint:
            print(re.sub("\n{3,}", "\n\n", text))

        attempt_count = 0
        max_attempts = 3
        t_text = ""

        # It will attempt to get a translation a set number of times
        while attempt_count < max_attempts:
            try:
                t_text = self.get_translation(text)
                break
            except Exception as e:
                # If an exception is encountered, it will sleep for a certain amount of time and try again
                sleep_time = int(60 / self.key_len)
                print(e, f"will sleep {sleep_time} seconds")
                time.sleep(sleep_time)
                attempt_count += 1
                if attempt_count == max_attempts:
                    print(f"Get {attempt_count} consecutive exceptions")
                    raise

        if needprint:
            print("[bold green]" + re.sub("\n{3,}", "\n\n", t_text) + "[/bold green]")

        elapsed_time = time.time() - start_time

        return t_text

        # This method translates the text and splits it into lines

    def translate_and_split_lines(self, text):
        result_str = self.translate(text, False)
        lines = result_str.split("\n")
        lines = [line.strip() for line in lines if line.strip() != ""]
        return lines

        # This method attempts to get the best result list

    def get_best_result_list(
            self,
            plist_len,
            new_str,
            sleep_dur,
            result_list,
            max_retries=15,
    ):
        if len(result_list) == plist_len:
            return result_list, 0

        best_result_list = result_list
        retry_count = 0

        while retry_count < max_retries and len(result_list) != plist_len:
            print(
                f"bug: {plist_len} -> {len(result_list)} : Number of paragraphs before and after translation",
            )
            print(f"sleep for {sleep_dur}s and retry {retry_count + 1} ...")
            time.sleep(sleep_dur)
            retry_count += 1
            result_list = self.translate_and_split_lines(new_str)
            if (
                    len(result_list) == plist_len
                    or len(best_result_list) < len(result_list) <= plist_len
                    or (
                    len(result_list) < len(best_result_list)
                    and len(best_result_list) > plist_len
            )
            ):
                best_result_list = result_list

        return best_result_list, retry_count

        # This method logs retries

    def log_retry(self, state, retry_count, elapsed_time, log_path="log/buglog.txt"):
        if retry_count == 0:
            return
        print(f"retry {state}")
        with open(log_path, "a", encoding="utf-8") as f:
            print(
                f"retry {state}, count = {retry_count}, time = {elapsed_time:.1f}s",
                file=f,
            )

def log_translation_mismatch(
        self,
        plist_len,
        result_list,
        new_str,
        sep,
        log_path="log/buglog.txt",
    ):
        if len(result_list) == plist_len:
            return
        newlist = new_str.split(sep)
        with open(log_path, "a", encoding="utf-8") as f:
            print(f"problem size: {plist_len - len(result_list)}", file=f)
            for i in range(len(newlist)):
                print(newlist[i], file=f)
                print(file=f)
                if i < len(result_list):
                    print("............................................", file=f)
                    print(result_list[i], file=f)
                    print(file=f)
                print("=============================", file=f)

        print(
            f"bug: {plist_len} paragraphs of text translated into {len(result_list)} paragraphs",
        )
        print("continue")

def join_lines(self, text):
    lines = text.split("\n")
    new_lines = []
    temp_line = []

    # join
    for line in lines:
        if line.strip():
            temp_line.append(line.strip())
        else:
            if temp_line:
                new_lines.append(" ".join(temp_line))
                temp_line = []
            new_lines.append(line)

    if temp_line:
        new_lines.append(" ".join(temp_line))

    text = "\n".join(new_lines)

    # del ^M
    text = text.replace("^M", "\r")
    lines = text.split("\n")
    filtered_lines = [line for line in lines if line.strip() != "\r"]
    new_text = "\n".join(filtered_lines)

    return new_text

def translate_list(self, plist):
    sep = "\n\n\n\n\n"
    # new_str = sep.join([item.text for item in plist])

    new_str = ""
    i = 1
    for p in plist:
        temp_p = copy(p)
        for sup in temp_p.find_all("sup"):
            sup.extract()
        new_str += f"({i}) {temp_p.get_text().strip()}{sep}"
        i = i + 1

    if new_str.endswith(sep):
        new_str = new_str[: -len(sep)]

    new_str = self.join_lines(new_str)

    plist_len = len(plist)

    print(f"plist len = {len(plist)}")

    result_list = self.translate_and_split_lines(new_str)

    start_time = time.time()

    result_list, retry_count = self.get_best_result_list(
        plist_len,
        new_str,
        6,
        result_list,
    )

    end_time = time.time()

    state = "fail" if len(result_list) != plist_len else "success"
    log_path = "log/buglog.txt"

    self.log_retry(state, retry_count, end_time - start_time, log_path)
    self.log_translation_mismatch(plist_len, result_list, new_str, sep, log_path)

    # del (num), num. sometime (num) will translated to num.
    result_list = [re.sub(r"^(\(\d+\)|\d+\.|(\d+))\s*", "", s) for s in result_list]
    return result_list

def set_deployment_id(self, deployment_id):
    openai.api_type = "azure"
    openai.api_version = "2023-03-15-preview"
    self.deployment_id = deployment_id

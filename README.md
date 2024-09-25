# book-summarizer
Book summarizer is a Python app made with Tkinter which leverages different LLM providers to summarize given books into a 500-1000 words final summary.

The app calls different providers or runs local inference to summarize chunks of the book's content until done. Then, the summaries are reprocessed into a final summary.

It is designed with Calibre library folders in mind, but can work with the raw files too, just not in the way I use it (to add summaries as descriptions, which uses the metadata added to the summary).

Best (and truly, only effective models) for this task are:
- GPT-4o
- GPT-4o-mini (can hallucinate a bit)
- Gemini-1.5-pro (best one in my testing due to its long context)
- Gemini-1.5-flash (does hallucinate more)
- Claude-3.5-sonnet
- Qwen-2.5-72b (price/performance undeniable king)
- Llama-3.1-70b (can hallucinate a bit)

I've yet to test the newly released llama 3.2-11b and 90b models, and Qwen2.5-32b.

---------

Run the TKinter app with `python app.py`

---------

Currently the models and providers are hardcoded, future updates will use web scraping and api calls to check the available models. You can edit this file but remember to revert it if pulling the latest updates.

The price and time calculations are based on local estimates (GTX 1070, 16GB of RAM & Ryzen 2600 combo), or data from https://artificialanalysis.ai/models.

Using LM Studio requires an active server instance using the chosen model.

API keys are hashed outside of the program and will only be used within the app execution.

AI wrote something like 70% of this release. I used GPT-4o, Claude 3.5 Sonnet, Deepseek 2.5 Coder and Qwen 2.5 72b interchangeably.

I dedicated most of my time to (painful) debugging, coordinating requests, merging and improving the AI's output.

---------

To do:

- <s>Add a `max_tokens` scrollbar widget to allow the user to define the max tokens and indirectly, the chunk size.</s>
- Add a button to reset already processed books, to allow for reprocessing. Right now you can remove and re-add.
- Add functionality to save processed and aborted books, and to not add them to the treeview if they were previously processed. This will be a toggle.
- Create a command line interface and maybe a pip package if I have time.

---------

Thanks.

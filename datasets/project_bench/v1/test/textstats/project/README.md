# textstats

Word statistics and readability scores for a folder of plain-text documents.

`build_report(corpus_root, output, settings_path)` walks the corpus folder, reads every
`.txt` file (UTF-8, or Windows-1252 for older files), skips documents that repeat an
earlier one, and writes one CSV row per document: word and sentence counts, average word
length, lexical diversity, Flesch reading ease, Flesch-Kincaid grade, and the most frequent
words and n-grams.

A corpus can also come with an `index.txt` that lists the documents to read, one path per
line relative to the corpus folder; `load_index(root)` reads those.

Settings live in an INI file (section `[textstats]`) or a JSON object:

```ini
[textstats]
lowercase = yes
min_word_length = 2
ngram_size = 2
top_words = 5
min_count = 2
stopwords = the, a, an, of
columns = document, words, sentences, reading_ease, top_words
```

Run the tests with `python -m pytest`.

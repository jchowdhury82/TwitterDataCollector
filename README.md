# TwitterDataCollector
A simple twitter reader using tweepy package.  Uses Twitter API v2. 

### Motivation:

This is just a simple wrapper around the Tweepy API's 
- Client.search_recent_tweets
- tweepy.StreamingClient.filter

The goal was to scrape sample tweets that have a specific emoji.
This data was intended to be used for training and testing a model which predicts emojis for a tweet

### Prerequisite:

Twitter developer account and project is required with simple Development access level
A bearer_token is to be generated and used for connecting the client.
Due to the least access level, tweets are restricted to last 7 days.

### Helper notebooks:
Tweepy_functions_simply_explained.ipynb : this explains how the Tweepy methods based on the Twitter V2 API works
Using_TwitterSampler.ipynb : this explains how the module TwitterSampler is used in a notebook


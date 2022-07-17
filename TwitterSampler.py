"""Wrapper for Tweepy (on Twitter v2)  for extracting sample tweets

Author: Joyjit Chowdhury

This script allows the user to extract tweets from Twitter using the Tweepy package(Twitter v2) in
the following ways:
1. Extract recent tweets from the last seven days that match a search query
2. Stream recent tweets in real time using a search query

Import for notebooks (provided TwitterSampler.py is in the PATH / PYTHONPATH):

    import sys
    sys.path.append('<some_path>/TwitterSampler.py')

    from TwitterSampler import TwitterSampler


Command Line invocation:

1. tweets_by_query:
python TwitterSampler.py tweets_by_query --max_tweets 5 --query_string happiness --config_file my_file.json

2. stream_tweets:
python TwitterSampler.py stream_tweets --max_tweets 5 --query_string elon musk
"""
import argparse
import json
import re
import sys
import advertools as adv
from datetime import datetime
import pandas as pd
import tweepy


def cleanup_tweet(tweet):
    """Simple regex to clean up tweets - remove extra spaces, special chars, @ mentions and hashtags"""
    return ' '.join(re.sub("([@#][\w:]+)|(\w+://\S+)|(\|)|(\.{2,})|(&amp;|&gt;)", " ", tweet).split()).lower()


class TweetWithEmoji(tweepy.tweet.Tweet):
    """
    Extend the Tweet class for adding new attributes

    Attributes:
    -------
    raw_tweet_text
    clean_tweet_text
    word_count
    emoji_list - list of emoji's in the tweet text
    emoji_seq_nbr - reference id of emoji's in tweet text. Ref IDs are in emoji_df.csv
    """

    def __init__(self, tweet):
        tweepy.tweet.Tweet.__init__(self, tweet.data)
        self.tweet_created_at = tweet.created_at.strftime('%Y-%m-%d %H:%M:%S')
        self.raw_tweet_text = tweet.text
        # add clean tweets and word count
        self.clean_tweet_text = cleanup_tweet(tweet.text)
        self.word_count = len(re.findall(r"\w+", self.clean_tweet_text))

        # add emojis
        emj_dict = adv.extract_emoji([self.clean_tweet_text])
        self.emoji_list = emj_dict['emoji_flat']
        if len(self.emoji_list) > 0:
            reference_emoji_df = adv.emoji_df['emoji'].reset_index().rename(columns={'index': 'emoji_seq_nbr'})
            input_emoji_list_df = pd.DataFrame(self.emoji_list, columns=['emoji'])
            self.emoji_seq_nbr = pd.merge(reference_emoji_df, input_emoji_list_df, on='emoji')['emoji_seq_nbr'].values
        else:
            self.emoji_seq_nbr = []


class TwitterSampler:
    """
    A class used to represent a TwitterSampler object which has the methods to extract Tweets

    Methods
    -------
    - get_tweets_by_query(self, query_string, max_tweets=100)
        Extract tweets using a standard Twitter search string using search words

    - stream_tweets(self, query_string, max_tweets=10, destination='stdout')
        Stream tweets using a standard Twitter search string using search words
    """

    def __init__(self, config_file='.twitter_config.json'):
        """
            Initialize a client using a bearer token. The bearer token is obtained from Twitter Developer portal.
            The token is passed in a configuration json file with structure:
            {
            "bearer" : "<bearer token string>"
            }

            The default filename is ".twitter_config.json"

        """
        try:
            with open(config_file) as f:
                config = json.load(f)

            self._bearer_token = config['bearer']
            self._client = tweepy.Client(bearer_token=self._bearer_token)

        except FileNotFoundError:
            print("Config file not found.")
        except Exception as client_error:
            print(f"Error in connecting to twitter API : {client_error}")

    def get_tweets_by_query(self, query_string, max_emojis=1, max_words=10, max_tweets=100):
        """
            Get tweets using a query string
            Input is a query string with search words or emoji's
            Eg: "happiness OR happy" if either word is searched using OR logic.
                "happiness happy"  if both words are searched using AND logic. Note there is no AND keyword, just space

            Exclude retweets to avoid duplicates
            At most 100 tweets can be extracted
            Tweets from last 7 days max

            Return: dataframe for matched tweets with columns ['id', 'created_at', 'tweet', 'lang']
        """

        # Build query string that conforms to Twitter API specifications
        query_string = query_string.replace(',', ' ').replace('+', ' ').replace(r' +', ' ')
        query = f'({query_string}) -is:retweet lang:en'
        # print(f"Running query : {query}")

        tweetlist = list()
        tweet_count = 0
        last_tweet = None
        # Use the Paginator method to get matching tweets 100 at a time into an iterator
        # Extract tweet fields for each tweet found
        while tweet_count <= max_tweets:
            for tweet in tweepy.Paginator(self._client.search_recent_tweets,
                                          query=query,
                                          until_id=last_tweet,
                                          tweet_fields=['id,created_at,text,lang'],
                                          max_results=100).flatten(limit=100):

                tweet_with_emojis = TweetWithEmoji(tweet)

                if 0 < len(tweet_with_emojis.emoji_list) <= max_emojis and tweet_with_emojis.word_count <= max_words:
                    tweetlist.append((tweet_with_emojis.id,
                                      tweet_with_emojis.tweet_created_at,
                                      tweet_with_emojis.raw_tweet_text,
                                      tweet_with_emojis.clean_tweet_text,
                                      tweet_with_emojis.lang,
                                      tweet_with_emojis.emoji_list,
                                      tweet_with_emojis.emoji_seq_nbr))
                    tweet_count = tweet_count + 1
                    if tweet_count > max_tweets:
                        break

                # we continue searching back until the desired tweet count is reached
                last_tweet = tweet_with_emojis.id

        # Convert the consolidated list "tweetlist" into a dataframe and return
        dftweets = pd.DataFrame(tweetlist, columns=['id', 'created_at', 'raw_tweet_text', 'clean_tweet_text',
                                                    'lang', 'emoji_list', 'emoji_seq_nbr'])
        return dftweets

    def stream_tweets(self, query_string, max_emojis=1, max_words=10, max_tweets=10, destination=None):
        """
            Stream tweets
            Input is
            1. a query string with search words or emoji's
            Eg: "happiness OR happy" if either word is searched using OR logic.
                "happiness happy"  if both words are searched using AND logic. Note there is no AND keyword, just space
            2. Destination where tweets are to be dumped - either stdout or a file

            Exclude retweets to avoid duplicates
            Tweets from last 7 days max

            Initiates a stream of Tweets that match the search criteria dumped to a destination
        """

        class TwitterStreamClient(tweepy.StreamingClient):
            """
                Extend the StreamingClient base class to add custom code
                Attributes
                ----------
                tweet_counter : str
                    a formatted string to print out what the animal says
                max_items : str
                    the name of the animal
                start_time : str
                    the sound that the animal makes
                outfile : int
                    the number of legs the animal has (default 4)
            """

            def __init__(self, max_items):
                """
                Initialize the extended streaming client with new members
                """
                try:
                    self.outer = TwitterSampler()
                    self.tweet_counter = 0
                    self.max_items = max_items
                    self.start_time = None
                    self.outfile = sys.stdout if destination is None else open(destination, 'w+')
                    # initialize base class with the bearer token initialized in the outer class
                    tweepy.StreamingClient.__init__(self, bearer_token=self.outer._bearer_token)

                except Exception as e_inner:
                    print(f"Error Initializing TwitterStreamClient = {e_inner}")

            def on_connect(self):
                """ initialize output stream when the client is connected """
                self.start_time = datetime.now()
                self.outfile.write('tweet_counter|id|created_at|cleaned_text|lang|emoji_list|emoji_seq_nbr\n')
                self.outfile.flush()

            def on_disconnect(self):
                """ close output stream when the client is disconnected  """
                print("Disconnected from twitter api")
                if destination is not None:
                    print(f"Tweets saved in {destination}")
                self.outfile.flush()
                self.outfile.close()

            def on_keep_alive(self):
                """ close output stream if no matching tweet is found in the last 60 seconds """
                cur_time = datetime.now()
                elapsed = cur_time - self.start_time
                if elapsed.seconds > 60 and self.tweet_counter == 0:
                    print("No tweets found for one minute")
                    self.disconnect()

            def on_response(self, response):
                """ parse tweet, format and write to output sink """

                # get the Tweet object from the response
                tweet_with_emojis = TweetWithEmoji(tweet=response.data)

                if 0 < len(tweet_with_emojis.emoji_list) <= max_emojis and tweet_with_emojis.word_count <= max_words:
                    counter = self.tweet_counter
                    tid = tweet_with_emojis.id
                    created = tweet_with_emojis.tweet_created_at
                    text = tweet_with_emojis.clean_tweet_text
                    lang = tweet_with_emojis.lang
                    emoji = ','.join(tweet_with_emojis.emoji_list)
                    emoji_id = ','.join(map(str, tweet_with_emojis.emoji_seq_nbr))

                    tweet_string = f"{counter}|{tid}|{created}|{text}|{lang}|{emoji}|{emoji_id}"
                    self.tweet_counter += 1
                    if destination is not None:
                        print(f"Tweet Count : {self.tweet_counter}")
                    self.outfile.write(f'{tweet_string}\n')
                    self.outfile.flush()

                # if max items is reached, then disconnect
                if self.tweet_counter == self.max_items:
                    print(f"Max items = {self.max_items} reached. Disconnecting from Twitter.")
                    self.disconnect()

            def on_request_error(self, status_code):
                """ For any request error, print the message and disconnect the client """
                print(f"Request error: {status_code}")
                self.disconnect()

        # initialize TwitterStreamClient object

        stream = TwitterStreamClient(max_items=max_tweets)

        try:
            # add filter rules using the input search string "query_string"

            existing_rules = stream.get_rules().data

            if existing_rules is not None:
                stream.delete_rules(ids=[rule.id for rule in existing_rules])

            query_string = query_string.replace(',', ' ').replace('+', ' ').replace(r' +', ' ')
            query = f'({query_string}) -is:retweet lang:en'

            # each rule is an object build from the query_string that needs to be attached to the stream
            rule = tweepy.StreamRule(query)
            stream.add_rules(rule)
            # Initiate the filtered stream
            stream.filter(tweet_fields=['id,created_at,text,lang'])

        except KeyboardInterrupt:
            print("Streaming stopped by user")
            stream.disconnect()

        except Exception as e:
            print(f"Error in streaming tweets : {e}")
            stream.disconnect()


# Handle argument parsing and method calling for command line execution
if __name__ == '__main__':

    parser = argparse.ArgumentParser()

    # config file is optional, by default it is .twitter_config.json on the same directory
    parser.add_argument('--config_file',
                        type=str,
                        required=False,
                        default='.twitter_config.json')

    parser.add_argument('--mode', type=str, required=False, choices=['query_tweets', 'stream_tweets'])

    parser.add_argument('--query_string', type=str, required=False)
    parser.add_argument('--max_tweets', type=int, required=False, default=100)
    parser.add_argument('--max_words', type=int, required=False, default=10)
    parser.add_argument('--max_emojis', type=int, required=False, default=1)
    parser.add_argument('--destination', type=str, required=False)

    # Parse the arguments
    args = parser.parse_args()

    # get TwitterSampler object
    ts = TwitterSampler(config_file=args.config_file)

    # Call functions accordingly
    if args.mode == 'query_tweets':
        df = ts.get_tweets_by_query(query_string=args.query_string,
                                    max_emojis=args.max_emojis,
                                    max_words=args.max_words,
                                    max_tweets=args.max_tweets)
        print(df.to_csv(sep='|'))

    if args.mode == 'stream_tweets':
        ts.stream_tweets(query_string=args.query_string,
                         max_emojis=args.max_emojis,
                         max_words=args.max_words,
                         max_tweets=args.max_tweets,
                         destination=args.destination)

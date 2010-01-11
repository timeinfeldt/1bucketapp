import cgi
import os
from google.appengine.api import users
from google.appengine.ext.webapp.util import run_wsgi_app
from google.appengine.ext import webapp
from google.appengine.ext.webapp import util
from google.appengine.ext import db
# python 2.5.2 imports
from urlparse import urlparse
#python 2.6 import
#from urlparse import urlparse, parse_qs
from google.appengine.ext.webapp import template
import re
from datetime import datetime
import urllib
import urllib2
import simplejson
import BeautifulSoup 
import tweepy
#authData.py containing Twitter auth
import authData

#load custom django template filters
webapp.template.register_template_library('customfilters')

class Bucket(db.Model):
    title = db.StringProperty()
    date = db.DateTimeProperty(auto_now_add=True)
    urlTitle = db.StringProperty()

class Author(db.Model):
    #full twitter username
    name = db.StringProperty()
    #twitter profile picture
    img = db.StringProperty()
    #twitter user id
    screenName = db.StringProperty()
    
class Tweet(db.Model):
    bucket = db.ReferenceProperty(Bucket)
    author = db.ReferenceProperty(Author)
    #raw text of the tweet
    text = db.StringProperty(multiline=True)
    #text between bucket and url, colon?
    headline = db.StringProperty(multiline=True)
    #content after headline, mainly url
    content = db.StringProperty(multiline=True)
    #original tweet date stamp
    date = db.DateTimeProperty()
    #unique tweet id
    tweetId = db.IntegerProperty()
    #embeddable object for templates
    embeddable = db.TextProperty()

def titleToUrlTitle(title):
    title = title.lower()
    title = urllib.quote(title, safe='')
    return title

def getYoutubeId(url):
    try:
        #return parse_qs(urlparse(url).query)['v'][0]
        return cgi.parse_qs(urlparse(url).query)['v'][0]
        
    except:
        raise Exception("Not a valid youtube URL!")
    return

def getVimeoId(url):
    try:
        return re.findall(r"vimeo\.com\/(.[0-9]*)", url)
    except:
        raise Exception("Not a valid vimeo URL!")
    return

def parseUrl(url):
    #url = url.lower()
    if (re.findall(r"vimeo\.com", url)):
        vimeoId = getVimeoId(url)[0]
        vimeoEmbed = '<object width="480" height="360"><param name="allowfullscreen" value="true" /><param name="allowscriptaccess" value="always" /><param name="movie" value="http://vimeo.com/moogaloop.swf?clip_id=' + vimeoId + '&amp;server=vimeo.com&amp;show_title=1&amp;show_byline=1&amp;show_portrait=0&amp;color=&amp;fullscreen=1" /><embed src="http://vimeo.com/moogaloop.swf?clip_id=' + vimeoId + '&amp;server=vimeo.com&amp;show_title=1&amp;show_byline=1&amp;show_portrait=0&amp;color=&amp;fullscreen=1" type="application/x-shockwave-flash" allowfullscreen="true" allowscriptaccess="always" width="480" height="360"></embed></object>'
        return vimeoEmbed
    
    if (re.match(r"^(https?://www\.youtube.com\/watch\?)", url)):
        youtubeId = getYoutubeId(url)
        if youtubeId:
            youtubeEmbed = '<object width="480" height="385"><param name="movie" value="http://www.youtube.com/v/' + youtubeId + '&hl=de_DE&fs=1&"></param><param name="allowFullScreen" value="true"></param><param name="allowscriptaccess" value="always"></param><embed src="http://www.youtube.com/v/' + youtubeId + '&hl=en_EN&fs=1&" type="application/x-shockwave-flash" allowscriptaccess="always" allowfullscreen="true" width="480" height="385"></embed></object>'
        return youtubeEmbed
    
    elif (re.match(r"^.*\.(tiff|pdf|ppt)$", url)):
        docUrlEncoded = urllib.quote(url, safe='')
        googleEmbed = '<iframe src="http://docs.google.com/viewer?url=' + docUrlEncoded + '&embedded=true" width="480" height="500" style="border: none;"></iframe>'
        return googleEmbed

    elif (re.match(r"^.*\.(jpg|png|gif|jpeg)$", url)):
        imgTag = '<img src="' + url + '" />'
        return imgTag

    else:
        soup = BeautifulSoup.BeautifulSoup(urllib.urlopen(url))
        pageTitle = soup.title.string
        pageTitleTag = '<a href="' + url + '">' + pageTitle + '</a>'
        return pageTitleTag

class ShowBucket(webapp.RequestHandler):
  def get(self, bucketUrl):
    bucketQuery = Bucket.gql("WHERE urlTitle = :urlTitle ORDER BY date DESC",
                             urlTitle=bucketUrl.lower())
    #bucket exists
    if (bucketQuery.count() > 0):
        bucket = bucketQuery[0]
        tweets = bucket.tweet_set.order('-date')
        #bucket is not empty
        if (tweets.count() > 0):
            #uniquifying the author list
            author_keys = set(Tweet.author.get_value_for_datastore(x) for x in tweets)
            authors = db.get(author_keys)
            
            template_values = {
                'authors': authors,
                'tweets': tweets,
                'bucket': bucket,
                }
            path = os.path.join(os.path.dirname(__file__), 'showBucket.html')
            
        #bucket is empty
        else:
            template_values = {
                'bucket': bucket,
                }
            path = os.path.join(os.path.dirname(__file__), 'showEmptyBucket.html')

    #bucket does not exist
    else:
        error = 'There is no bucket called ' + bucketUrl + ' :('
        template_values = {
            'error': error
            }
        path = os.path.join(os.path.dirname(__file__), 'error.html')

    self.response.out.write(template.render(path, template_values))

class NewBucket(webapp.RequestHandler):
    def post(self):
        bucket = Bucket.get_or_insert(self.request.get('title'),
                                      title = self.request.get('title'),
                                      urlTitle = titleToUrlTitle(self.request.get('title')))

        self.redirect('/buckets/' + bucket.urlTitle)

class MainPage(webapp.RequestHandler):
  def get(self):
    #list all buckets and tweets
    buckets = Bucket.all()
    buckets.order('date')
        
    template_values = {
        'buckets': buckets
        }
    path = os.path.join(os.path.dirname(__file__), 'index.html')
    self.response.out.write(template.render(path, template_values))

class Fetch(webapp.RequestHandler):
  def get(self):
    #auth for REST API
    auth = tweepy.BasicAuthHandler(authData.user, authData.password)
    api = tweepy.API(auth)

    #get all tweets that mention @1b
    tweets = api.mentions()

    #split and parse the tweets
    for i in tweets:
        text = i.text.encode('utf-8')
        parts = text.split()
        if (len(parts) >= 3 and parts[0] == '@1b'):

            #is there already a bucket with this title?
            tweetBucket = Bucket.get_or_insert(parts[1].lower(),
                                               title = parts[1],
                                               urlTitle = titleToUrlTitle(parts[1]))

            #does the author exist?
            tweetAuthor = Author.get_or_insert(i.user.screen_name,
                                                  name=i.user.name,
                                                  img = i.user.profile_image_url,
                                                  screenName = i.user.screen_name.encode('utf-8'))

            #set db fields that are already known by this point
            tweet = Tweet()
            tweet.bucket = tweetBucket
            tweet.author = tweetAuthor
            tweet.tweetId = i.id

            #query db to see if tweet is unique
            idQuery = Tweet.gql("WHERE tweetId = :tweetId ORDER BY date DESC",
                                tweetId=i.id)

            existingTweetId = idQuery.fetch(1)

            #if tweet is unique parse and pass to db
            if len(existingTweetId) < 1:
                tweet.date = i.created_at
                tweet.text = i.text
                #split headline and content
                contentParts = parts[2:]

                #find content urls
                urlPattern = re.compile(r"\b(([\w-]+://?|www[.])[^\s()<>]+(?:\([\w\d]+\)|))")
                contentUrls = []
                contentHeadline = contentParts
                for contentPart in contentParts:
                    if (re.findall(urlPattern, contentPart)):
                        contentUrls.append(contentPart)
                        contentHeadline.remove(contentPart)
                        
                        #unmask the tweet url to get past shorteners etc
                        url = contentUrls[0]
                        insideUrl = urllib.urlopen(url).geturl()
                        tweet.content = insideUrl

                        #parse the content and create embeddable object
                        tweet.embeddable = parseUrl(insideUrl)

                if (len(contentUrls) < 1):
                        tweet.embeddable = ' '.join(contentParts)
     
                #for now, headline is what's left over
                contentHeadlineString = ' '.join(contentHeadline)
                if contentHeadlineString:
                    tweet.headline = contentHeadlineString
                else:
                    tweet.headline = 'untitled'
                tweet.put()
                
application = webapp.WSGIApplication(
                                     [('/', MainPage),
                                      ('/fetch', Fetch),
                                      ('/new', NewBucket),
                                      (r'/buckets/(.*)', ShowBucket)
                                      ],
                                     debug=True)

def main():
    run_wsgi_app(application)

if __name__ == "__main__":
    main()

#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright 2012 Niphlod <niphlod@gmail.com>
#
# This file is part of w2p_tvseries.
#
# w2p_tvseries is free software; you can redistribute it and/or modify it under
# the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# w2p_tvseries is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with w2p_tvseries. If not, see <http://www.gnu.org/licenses/>.

from gluon.storage import Storage
try:
    import requests as req
except:
    raise ImportError , "requests module is needed: http://docs.python-requests.org"

import re
from email.utils import parsedate_tz, mktime_tz
import datetime

try:
  from lxml import etree
except ImportError:
  try:
    # Python 2.5
    import xml.etree.cElementTree as etree
  except ImportError:
    try:
      # Python 2.5
      import xml.etree.ElementTree as etree
    except ImportError:
      try:
        # normal cElementTree install
        import cElementTree as etree
      except ImportError:
        try:
          # normal ElementTree install
          import elementtree.ElementTree as etree
        except ImportError:
          print("Failed to import ElementTree from any known place")

import urllib
from gluon.contrib import simplejson as sj
from w2p_tvseries_utils import tvdb_logger, Meddler
import hashlib
import os

from gluon import current
import thread

locker = thread.allocate_lock()

def w2p_tvseries_feed_loader(*args, **vars):
    locker.acquire()
    type = args[0]
    args = args[1:]
    try:
        if not hasattr(w2p_tvseries_feed_loader, 'w2p_tvseries_feed_loader_instance_%s' % (type)):
            types = dict(
                Eztv_feed=Eztv_feed,
                Torrentz_feed=Torrentz_feed,
            )
            setattr(w2p_tvseries_feed_loader, 'w2p_tvseries_feed_loader_instance_%s' % (type),  types[type](*args, **vars))
    finally:
        locker.release()
    return getattr(w2p_tvseries_feed_loader, 'w2p_tvseries_feed_loader_instance_%s' % (type))


def w2p_tvseries_torrent_loader(*args, **vars):
    locker.acquire()
    try:
        if not hasattr(w2p_tvseries_torrent_loader, 'w2p_tvseries_torrent_instance'):
            w2p_tvseries_torrent_loader.w2p_tvseries_torrent_instance = w2p_tvseries_torrent(*args, **vars)
    finally:
        locker.release()
    return w2p_tvseries_torrent_loader.w2p_tvseries_torrent_instance

class w2p_tvseries_torrent(object):

    def __init__(self):
        self.logger = tvdb_logger('torrent')
        self.req = req.session(headers = {'User-Agent' : 'w2p_tvdb'})
        self.magnetr = re.compile(r'xt=urn:btih:([\w]{40})&')

    def log(self, function, message):
        log = self.logger
        log.log(function, message)

    def error(self, function, message):
        log = self.logger
        log.error(function, message)

    def get_torrent_from_magnet(self, magnet):
        hash = self.magnetr.search(magnet)
        if hash:
            hash = hash.group(1).upper()
            return "http://torrage.com/torrent/%s.torrent" % (hash)
        else:
            return None

    def queue_torrents(self, seriesid, seasonnumber):
        fname = 'queue_torrents'
        db = current.database
        ss = db.seasons_settings
        rec = db(
            (db.series.id == seriesid) &
            (db.seasons_settings.series_id == db.series.id) &
            (db.seasons_settings.seasonnumber == seasonnumber)
            ).select().first()

        if not rec or not rec.seasons_settings.torrent_tracking:
            self.error(fname, "Can't find settings for season %s season %s" % (seriesid, seasonnumber))
            return
        try:
            settings = sj.loads(rec.seasons_settings.torrent_settings)
        except:
            self.error(fname, "Can't load settings for season %s season %s" % (seriesid, seasonnumber))
            return
        settings = Storage(settings)
        """{"feed": "eztv", "season": 8, "show_name": "24", "minsize": 100, "maxsize": 4780, "quality": "", "lower_attention" : "Verified"}"""
        base_avoid = db(
            (db.episodes.seriesid == db.series.seriesid) &
            (db.series.id == seriesid) &
            (db.episodes.seasonnumber == seasonnumber)
            )
        eps_to_avoid = base_avoid(db.episodes.tracking == False)
        downloaded = base_avoid(
            (db.downloads.episode_id == db.episodes.id) &
            (db.episodes.tracking == True) &
            (db.downloads.queued == True)
            )
        feed = w2p_tvseries_feed_loader(settings.feed)
        try:
            settings.season = int(settings.season)
        except:
            pass
        settings.minsize = int(settings.minsize)
        settings.maxsize = int(settings.maxsize)
        eps = feed.search(settings.show_name, settings.season, settings.quality, settings.minsize, settings.maxsize, settings.regex, settings.lower_attention)
        eps_to_avoid = eps_to_avoid.select(db.episodes.number)
        downloaded = downloaded.select(db.episodes.number)
        avoiding = [row.number for row in eps_to_avoid]
        avoiding.extend([row.number for row in downloaded])
        try:
            missing = sj.loads(rec.seasons_settings.season_status)
            missing = missing.get('missing', [])
        except:
            pass

        to_catch = []
        valid_eps = [ep for ep in eps if not ep.reason]
        for ep in valid_eps:
            for subep in ep.episodes:
                if subep in avoiding:
                    continue
                else:
                    if subep in missing:
                        to_catch.append(ep)
        for ep in to_catch:
            #find db.episodes.id
            episodes_ids = db(
                (db.episodes.number.belongs(ep.episodes)) &
                (db.episodes.seriesid == rec.series.seriesid) &
                (db.episodes.seasonnumber == seasonnumber)
                ).select()
            for row in episodes_ids:
                self.log(fname, "adding to queue %s - S%.2dE%.2d" % (rec.series.name, row.seasonnumber, row.number))
                to_insert = Storage()
                to_insert.type = 'torrent'
                to_insert.episode_id = row.id
                to_insert.guid = ep.guid
                to_insert.magnet = ep.magnet
                to_insert.link = ep.link
                to_insert.series_id = seriesid
                to_insert.seasonnumber = seasonnumber
                db.downloads.update_or_insert(db.downloads.guid==to_insert.guid, **to_insert)
        if len(avoiding) > 0:
            #prune relevant downloads records
            episodes_ids = db(
                (db.episodes.number.belongs(avoiding)) &
                (db.episodes.seriesid == rec.series.seriesid) &
                (db.episodes.seasonnumber == seasonnumber)
                )._select(db.episodes.id)
            db(db.downloads.episode_id.belongs(episodes_ids)).delete()

        db.commit()

    def downloader(self, url):
        db = current.database
        ct = db.urlcache
        cachekey = hashlib.md5(url).hexdigest()
        timelimit = datetime.datetime.utcnow() - datetime.timedelta(hours=3)
        cached = db((ct.key == cachekey) & (ct.inserted_on > timelimit)).select().first()
        if cached:
            self.log('downloader', '%s fetched from cache' % (url))
            return cached.value
        else:
            try:
                r = self.req.get(url)
                r.raise_for_status()
                content = r.content
                ct.update_or_insert(ct.key==cachekey, value=content, inserted_on=datetime.datetime.utcnow(), key=cachekey)
                db.commit()
                self.log('downloader', '%s fetched from internet' % (url))
            except:
                self.error('downloader', '%s failed to fetch from internet' % (url))
                content = None
        return content

    def download_torrents(self, seriesid, seasonnumber):
        fname = "down_torrents"
        db = current.database
        dw = db.downloads
        gs = db.global_settings
        torrent_path = db(gs.key == 'torrent_path').select().first()
        torrent_path = torrent_path and torrent_path.value or None
        #find torrents to download
        res = db(
            (dw.queued == False) &
            (dw.down_file == None) &
            (dw.series_id == seriesid) &
            (dw.seasonnumber == seasonnumber)
            ).select()
        for row in res:
            if not row.link:
                row.link = self.get_torrent_from_magnet(row.magnet)
                row.update_record(link=row.link)
            content = self.downloader(row.link)
            if content == None:
                newurl = self.get_torrent_from_magnet(row.magnet)
                if newurl:
                    content = self.downloader(newurl)
            if content == None:
                self.error(fname, "Can't download %s " % row.link)
            else:
                row.update_record(down_file=content)
        db.commit()
        if not torrent_path:
            self.error(fname, "torrent_path not set")
            return
        if not os.path.exists(torrent_path):
            self.error(fname, "torrent_path %s not found" % (torrent_path))
            return
        res = db(
            (dw.queued == False) &
            (dw.down_file != None) &
            (dw.series_id == seriesid) &
            (dw.seasonnumber == seasonnumber)
            ).select()
        for row in res:
            filename = row.link.split('/')[-1]
            filename = os.path.join(torrent_path, filename)
            try:
                with open(filename, 'wb') as g:
                    g.write(row.down_file)
                row.update_record(queued=True)
            except:
                self.error(fname, "Cannot write to %s" % (filename))
        db.commit()


class w2p_tvseries_feed(object):
    def __init__(self):
        self.logger = tvdb_logger('feeds')
        self.req = req.session(headers = {'User-Agent' : 'w2p_tvdb'})
        self.meddler = Meddler()

    def log(self, function, message):
        log = self.logger
        log.log(function, message)

    def error(self, function, message):
        log = self.logger
        log.error(function, message)

    def search(self, show_name, seasonnumber, quality='', minsize=100, maxsize=4780, regex=None, lower_attention='Verified'):
        self.eps = []
        self.calc_url_feed(show_name, seasonnumber, lower_attention)
        self.parse_feed()
        self.filter_list(quality, minsize*1024*1024, maxsize*1024*1024, regex, seasonnumber)
        return self.eps

    def calc_url_feed(show_name, seasonnumber):
        pass

    def get_torrent_from_hash(self, hash):
        hash = hash.upper()
        if len(hash) == 40:
            return "http://torrage.com/torrent/%s.torrent" % (hash)

    def retrieve_ttl(self, feed):
        root = etree.fromstring(feed)
        ttl = root.findtext('ttl')
        try:
            ttl = int(ttl)*60
        except:
            ttl = 15*60
        ttl = datetime.datetime.utcnow() + datetime.timedelta(seconds=ttl)
        return ttl

    def downloader(self, url):
        """manage ttl"""
        db = current.database
        ct = db.urlcache
        cachekey = hashlib.md5(url).hexdigest()
        timelimit = datetime.datetime.utcnow() - datetime.timedelta(seconds=3*60)
        cached = db((ct.key == cachekey) & (ct.inserted_on > timelimit)).select().first()
        if cached:
            self.log('downloader', '%s fetched from cache' % (url))
            return cached.value
        else:
            try:
                r = self.req.get(url)
                r.raise_for_status()
                content = r.content
                inserted_on = self.retrieve_ttl(content)
                ct.update_or_insert(ct.key==cachekey, value=content, inserted_on=inserted_on, key=cachekey)
                db.commit()
                self.log('downloader', '%s fetched from internet' % (url))
            except:
                content = None
                self.error('downloader', '%s failed to fetch from internet' % (url))
        return content

    def parse_feed(self):
        """return a list of dicts
        title
        seasonnumber
        episodenumber
        torrenturl
        magneturl
        guid
        """
        content = self.downloader(self.feed_url)
        root = etree.fromstring(content)
        eps = []
        for item in root.findall('channel/item'):
            eps.append(self.parse_item(item))
        self.eps = eps



    def parse_item(self, item):
        """return a dict
        title
        seasonnumber
        [episodes]
        torrenturl
        magneturl
        guid
        pubdate
        size
        """

    def parse_title(self, title):
        m = self.meddler.analyze(title)
        return m

    def filter_list(self, quality, minsize, maxsize, regex, seasonnumber):
        self.splitr = re.compile(r'[\s\[\]\(\)\.-]*')
        quality = [q for q in quality.split(',') if q <> '']
        qon = []
        qoff = []
        self.excluded = []
        for a in quality:
            if a.upper().startswith('NO_'):
                qoff.append(a.upper().replace('NO_', '',1))
            else:
                qon.append(a.upper())
        qon = set(qon)
        qoff = set(qoff)
        for i, a in enumerate(self.eps):
            if a.reason:
                continue
            if seasonnumber <> 'ALL':
                seasonnumber = int(seasonnumber)
                if self.eps[i].seasonnumber <> seasonnumber:
                    self.eps[i].reason = "Season mismatch (%s vs %s)" % (self.eps[i].seasonnumber, seasonnumber)
                    continue
            m = self.splitr.split(a.filterwith.upper())
            m = [s for s in m if s <> '']
            m = set(m)
            if qoff:
                exclude = m & qoff
                if exclude:
                    self.eps[i].reason = "contains %s"  % ("and ".join(exclude))
                    continue
            if qon:
                include = m & qon
                if not include:
                    self.eps[i].reason = "not contains %s" % ("and ".join(qon))
                    continue
            if a.size >= maxsize:
                self.eps[i].reason = "exceeded max size (%s>=%s)" % (a.size/1024/1024, maxsize/1024/1024)
            elif a.size <= minsize:
                self.eps[i].reason = "exceeded min size (%s<=%s)" % (a.size/1024/1024, minsize/1024/1024)
            if regex:
                try:
                    regex_ = re.compile(regex)
                    if not regex_.search(a.filterwith.upper()):
                        self.eps[i].reason = "not matching regex '%s'" % (regex)
                except:
                    self.eps[i].reason = "invalid regex '%s'" % (regex)

        grouper = Storage()
        for i, ep in enumerate(self.eps):
            episodes = ep.episodes
            if ep.reason:
                continue
            for subep in episodes:
                if not grouper[subep]:
                    grouper[subep] = [i]
                else:
                    grouper[subep].append(i)

        for k,v in grouper.iteritems():
            maxsize = 0
            for ep in v:
                size = self.eps[ep].size / len(self.eps[ep].episodes)
                if self.eps[ep].size >= maxsize:
                    maxsize = self.eps[ep].size
            status = 0
            for ep in v:
                if not self.eps[ep].size == maxsize:
                    self.eps[ep].reason = "Better quality found in another torrent"
                else:
                    status = 1
            if not status:
                continue
            #if same size all
            better = []
            for ep in v:
                if '720P' in self.eps[ep].filterwith.upper():
                    better.append(ep)
            if len(better) > 0:
                for ep in v:
                    if ep in better:
                        continue
                    self.eps[ep].reason = "Found same episode with 720P quality"
            if len(v)>1:
                for i, ep in enumerate(v):
                    if i > 0:
                        self.eps[ep].reason = "Couldn't see the best episode, discarding the older ones"
                    else:
                        self.eps[ep].reason = None

        #proper checking
        for k,v in grouper.iteritems():
            proper = []
            for ep in v:
                if 'PROPER' in self.eps[ep].filterwith.upper() or 'REPACK' in self.eps[ep].filterwith.upper():
                    self.eps[ep].reason = None
                    proper.append(ep)
            if len(proper) > 0:
                for ep in v:
                    if ep not in proper:
                        self.eps[ep].reason = 'Proper found for the same episode'

class Eztv_feed(w2p_tvseries_feed):

    def __init__(self, *args):
        super(Eztv_feed, self).__init__(*args)
        self.magnetr = re.compile(r'info_hash=([\w]{40})')

    def calc_url_feed(self, show_name, seasonnumber, lower_attention):
        vars = dict(show_name=show_name, show_name_exact='true', season=seasonnumber, mode='rss')
        vars = urllib.urlencode(vars)
        feed = "http://www.ezrss.it/search/index.php?" + vars
        self.feed_url = feed

    def parse_item(self, item):
        ep = Storage()
        ep.filename = item.findtext('{http://xmlns.ezrss.it/0.1/}torrent/{http://xmlns.ezrss.it/0.1/}fileName')
        info = self.parse_title(ep.filename)
        ep.update(info)
        ep.title = item.findtext('title')
        ep.link = item.findtext('link')
        ep.description = item.findtext('description')
        ep.guid = item.findtext('guid')
        ep.pubdate = item.findtext('pubDate')
        ep.magnet = item.findtext('{http://xmlns.ezrss.it/0.1/}torrent/{http://xmlns.ezrss.it/0.1/}magnetURI')
        ep.filename = item.findtext('{http://xmlns.ezrss.it/0.1/}torrent/{http://xmlns.ezrss.it/0.1/}fileName')
        ep.pubdate = datetime.datetime.utcfromtimestamp(mktime_tz(parsedate_tz(ep.pubdate)))
        ep.size = item.find('enclosure').get('length')
        try:
            ep.size = int(ep.size)
        except:
            ep.size = 0
        if ep.size < 100*1024*1024:
            ep.size = 300*1024*1024
        if ep.magnet == 'magnet:?xt=urn:btih:&dn=':
            #check at least for a bt-chat info_hash
            btchat = self.magnetr.search(ep.link)
            if btchat:
                hash = btchat.group(1)
                ep.magnet = 'magnet:?xt=urn:btih:%s' % hash
                ep.link = None
        if not ep.guid:
            ep.guid = ep.description
        ep.filterwith = ep.title
        return ep

class Torrentz_feed(w2p_tvseries_feed):
    def __init__(self, *args):
        super(Torrentz_feed, self).__init__(*args)
        self.hashr = re.compile('Hash: ([\w]{40})$')
        self.sizer = re.compile('^Size: ([\d]*?) MB')

    def calc_url_feed(self, show_name, seasonnumber, lower_attention='Verified'):
        vars = dict(q=show_name)
        vars = urllib.urlencode(vars)
        if lower_attention == 'Verified':
            feed = "http://torrentz.eu/feed_verified?" + vars
        else:
            feed = "http://torrentz.eu/feed?" + vars
        self.feed_url = feed

    def parse_item(self, item):
        ep = Storage()
        ep.title = item.findtext('title')
        info = self.parse_title(ep.title)
        ep.update(info)
        ep.description = item.findtext('description')
        hash = self.hashr.search(ep.description)
        if hash:
            ep.hash = hash.group(1)
        if ep.hash:
            ep.magnet = "magnet:?xt=urn:btih:%s" % (ep.hash)
        size = self.sizer.search(ep.description)
        if size:
            ep.size = int(size.group(1))*1024*1024
        ep.filterwith = ep.title
        ep.guid = item.findtext('guid')
        if not ep.link and ep.hash:
            ep.link = self.get_torrent_from_hash(ep.hash)
        return ep
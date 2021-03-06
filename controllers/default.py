#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright 2013 Niphlod <niphlod@gmail.com>
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
from w2p_tvseries_utils import w2p_tvseries_settings
from w2p_tvseries_clients import w2p_tvseries_torrent_client_loader
from gluon.contrib import simplejson as sj

def index():
    settings_ = w2p_tvseries_settings()
    gsettings = settings_.global_settings()
    if len(gsettings) < 7:
        session.flash = "Please adjust your preferences"
        redirect(URL('settings'))
    return dict()

def settings():
    settings_ = w2p_tvseries_settings()
    settings = settings_.general_settings()
    gsettings = settings_.global_settings()

    for k,v in gsettings.iteritems():
        settings.defaults[k] = v

    fi = [
        Field(k, settings.types.get(k, 'string'), comment=settings.comments[k],
              default=settings.defaults[k], widget=settings.widgets[k], requires=settings.requires[k])
        for k in settings.fields
    ]

    form = SQLFORM.factory(
        *fi, submit_button="Save Settings"
    )
    form.wells = [
        dict(
            title="General Settings",
            fields=['series_language', 'season_path', 'series_basefolder',
                    'series_metadata', 'hash_gen']
        ),
        dict(
            title="Scooper Settings",
            fields=['scooper_path']
        ),
        dict(
            title="Torrent Defaults",
            fields=['torrent_path', 'torrent_magnet', 'torrent_default_feed',
                    'torrent_default_quality','torrent_default_minsize',
                    'torrent_default_maxsize']
        ),
        dict(
            title="Subtitles Settings",
            fields=['itasa_username','itasa_password','subtitles_default_method',
                    'subtitles_default_quality', 'subtitles_default_language']
        )
        ]

    if form.process(hideerror=True).accepted:
        for a in form.vars:
            if a == 'itasa_password':
                if form.vars[a] <> 8*('*'):
                    db.global_settings.update_or_insert(
                        db.global_settings.kkey == a,
                        value = form.vars[a], kkey=a
                        )
            elif a == 'series_basefolder':
                db.global_settings.update_or_insert(
                    db.global_settings.kkey == a,
                    value = form.vars[a].strip(),
                    kkey=a
                    ) ##FIXME
            elif a == 'scooper_path':
                values = form.vars[a]
                if not isinstance(values, (tuple,list)):
                    values = [values]
                values = [a.strip() for a in values if a.strip() != ''] #FIXME
                values = set(values)
                db(db.global_settings.kkey=='scooper_path').delete()
                for b in values:
                    db.global_settings.insert(kkey='scooper_path', value=b)
            else:
                db.global_settings.update_or_insert(
                    db.global_settings.kkey == a,
                    value = form.vars[a], kkey=a
                    )
        db.commit()
        settings_.global_settings(refresh=True)
        if form.vars.torrent_magnet == 'ST':
            if gsettings.tclient == 'None':
                session.flash = 'You need to configure your torrent client'
                redirect(URL('default', 'client_settings'))
        session.flash = 'settings updated correctly'
        redirect(URL(r=request, args=request.args))
    elif form.errors:
        response.flash = 'errors in form, please check'

    return dict(form=form)

def client_settings():
    settings_ = w2p_tvseries_settings()
    settings = settings_.torrent_client_settings()
    gsettings = settings_.global_settings()

    for k,v in gsettings.iteritems():
        settings.defaults[k] = v

    fi = [
        Field(k, settings.types.get(k, 'string'),
              comment=settings.comments[k],
              default=settings.defaults[k],
              label=settings.labels.get(k, k),
              widget=settings.widgets[k],
              requires=settings.requires[k]
              )
        for k in settings.fields
    ]

    form = SQLFORM.factory(
        *fi, buttons=[
            BUTTON("Save Changes", _class="btn btn-primary"),
            BUTTON("Try Connection", _class="btn btn-info tclient_validate",
                   _href=URL('default', 'client_settings_validate.load')
                   )
            ]
    )
    if form.process(hideerror=True).accepted:
        for a in form.vars:
            db.global_settings.update_or_insert(
                db.global_settings.kkey == a,
                value = form.vars[a],
                kkey=a
                )

        settings_.global_settings(refresh=True)
        session.flash = 'settings updated correctly'
        redirect(URL(r=request, args=request.args))

    elif form.errors:
        response.flash = 'errors in form, please check'

    return dict(form=form)

def client_settings_helper():
    client = request.args(0)
    if not client or client not in ('transmission', 'deluge', 'utorrent'):
        return sj.dumps(dict(error="No supported client"))

    mapping = dict(transmission=('admin', 'password', 'http://127.0.0.1:9091/transmission/rpc'),
                   deluge=('', 'deluge', 'http://127.0.0.1:8112/json'),
                   utorrent=('admin', 'password', 'http://127.0.0.1:8080/gui/'))

    return sj.dumps(mapping[client])

def client_settings_validate():
    if request.vars.tclient not in ('transmission', 'deluge', 'utorrent'):
        return sj.dumps(dict(error="Client is not supported"))
    tclient = w2p_tvseries_torrent_client_loader(request.vars.tclient)
    tclient.username = request.vars.tusername
    tclient.password = request.vars.tpassword
    tclient.url = request.vars.turl
    status = tclient.get_status()
    if status is None:
        return dict(status='error', message="Connection error, please check it out")
    else:
        return dict(status='ok', message='all ok')

def hints():
    session.forget(response)
    #are there any new season if we're following the last one ?

    ss = db.seasons_settings
    ep_me = db.episodes_metadata
    ep_tb = db.episodes
    se_tb = db.series
    dw_tb = db.downloads
    new_se = []
    all_se = db(se_tb.id > 0).select(se_tb.id, se_tb.name, se_tb.status)
    se_cache = {}
    for row in all_se:
        se_cache[row.id] = row

    lock_validate = cache.ram('lock_validate', lambda: request.now, time_expire=120)

    for row in all_se:
        if lock_validate == request.now:
            #validate seasons every two minutes at most
            validate_seasons(row.id)
        all_seasons = db(ss.series_id == row.id).select(
            ss.seasonnumber, ss.tracking,
            orderby=ss.seasonnumber
            )
        to_activate = False
        x = 0
        for a in all_seasons:
            x += 1
            if a.tracking:
                to_activate = True
            elif to_activate and not a.tracking:
                new_se.append(
                    Storage(id=row.id, name=row.name, seasonnumber=a.seasonnumber)
                    )
            #instead of doing another query, let's store in se_cache the last tracked season for every series
            if len(all_seasons) == x:
                se_cache[row.id]['lastseason'] = a.seasonnumber

    #are there any season we're following with all files in it?
    all_se = db(ss.tracking == True).select()
    completed_se = {}
    double_files = {}
    for row in all_se:
        rtn = db(
            (se_tb.id == row.series_id) &
            (ep_tb.seriesid == se_tb.seriesid) &
            (ep_tb.language == se_tb.language) &
            (ep_tb.seasonnumber == row.seasonnumber) &
            (ep_tb.tracking == True) &
            (
                (ep_me.id == None) |
                (ep_me.filename == None)
            )
          ).select(ep_tb.id, ep_me.id, left=ep_me.on(ep_me.episode_id==ep_tb.id))
        if not rtn and row.seasonnumber != se_cache[row.series_id]['lastseason']:
            if row.series_id in completed_se:
                completed_se[row.series_id].append(row.seasonnumber)
            else:
                completed_se[row.series_id] = [row.seasonnumber]
        #in the meantime, let's check if there are files
        #ready to be renamed but there is another valid one
        #yet in the folder
        data = sj.loads(row.season_status)
        existingvideo = data.get('existingvideo', [])
        existingsubs = data.get('existingsubs', [])
        if existingvideo or existingsubs:
            inner_report = {
                'seasonnumber' : row.seasonnumber,
                'videos' : existingvideo,
                'subs' : existingsubs
                }
            if row.series_id not in double_files:
                double_files[row.series_id] = [inner_report]
            else:
                double_files[row.series_id].append(inner_report)

    #are there any torrents that are giving us problems ?
    unable_to_download = {}
    counter = 0
    all_se = db((ss.tracking == True) & (ss.torrent_tracking == True)).select()
    for row in all_se:

        rtn = db(
            (se_tb.id == row.series_id) &
            (ep_tb.seriesid == se_tb.seriesid) &
            (ep_tb.language == se_tb.language) &
            (ep_tb.seasonnumber == row.seasonnumber) &
            (ep_tb.tracking == True) &
            (
                (ep_me.id == None) |
                (ep_me.filename == None)
            )
            &
            (dw_tb.episode_id == ep_tb.id) &
            (dw_tb.queued == False)
            ).select(left=ep_me.on(ep_me.episode_id==ep_tb.id))

        no_torrent = {}
        for irow in rtn:
            counter += 1
            no_torrent[irow.episodes.id] = {
                'link' : irow.downloads.link,
                'magnet' : irow.downloads.magnet,
                'queued_at' : irow.downloads.queued_at,
                'name' : irow.episodes.name,
                'epnumber' : irow.episodes.epnumber
            }
        if len(no_torrent) == 0:
            continue

        if row.series_id not in unable_to_download:
            unable_to_download[row.series_id] = {
                row.seasonnumber : no_torrent
            }
        else:
            unable_to_download[row.series_id][row.seasonnumber] = no_torrent


    return dict(
        new_se=new_se,
        completed_se=completed_se,
        se_cache=se_cache,
        double_files=double_files,
        unable_to_download=unable_to_download,
        unable_to_download_counter=counter
        )

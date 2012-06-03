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

import re
from gluon.storage import Storage
try:
    import requests as req
except:
    raise ImportError , "requests module is needed: http://docs.python-requests.org"

import os
import datetime
from w2p_tvseries_utils import myfolderwidget, myfolderwidgetmultiple, myradiowidget
import unicodedata

DEPOSIT_RE = re.compile(r"^([^\.]*\.[^\.]*)\.(.{2}).*$")

ICON_MAPPING = {
                   'Continuing' : 'icon-repeat',
                   'Ended' : 'icon-off',
                   'ok' : 'icon-ok',
                   'ko' : 'icon-remove',
                   'question' : 'icon-question-sign',
                   'downloading_magnet' : 'icon-magnet',
                   'add' : 'icon-plus',
                   'delete' : 'icon-remove',
                   'filter' : 'icon-filter',
                   'reset' : 'icon-repeat',
                   }

def w2p_icon(status, variant=None):
    variant = variant and ' icon-white' or ''
    return TAG[''](' ',I(_class="%s%s" % (ICON_MAPPING[status], variant), _title=status))


def wp2tv_sidebar(genre):

    if genre:
        basecond = db.series.genre.contains(genre)
    else:
        basecond = db.series.id>0
    sidebar_series = db(basecond).select(db.series.id, db.series.name, db.series.status, db.series.genre, orderby=db.series.name)
    genres = {}
    for row in sidebar_series:
        for g in row.genre:
            genres[g] = 1

    genres = sorted(genres.keys())
    script = """
$(function () {
    var el = $("#operation_button");
    var bar = $("#operation_progress");
    el.tooltip({placement : 'right'});
    el.click(function(e) {
        e.preventDefault();
        var url = $(this).attr('href');
        $(this).text('stopping...');
        var request = w2p_tvseries_ajax_page('get', url, null, '');
        $.when(request).then(function() {
            el.text('0/0');
        });

    });
    $.PeriodicalUpdater('/w2p_tvseries/log/op_status', {
        method: 'get',
        data: '',
        minTimeout: 1000,
        maxTimeout: 8000,
        multiplier: 2,
        type: 'json',
        maxCalls: 0,
        autoStop: 0,
    'beforeSend':function(xhr) {
        xhr.setRequestHeader('web2py-component-location', document.location);
        xhr.setRequestHeader('web2py-component-element', el.attr('id') );
        },
    },
    function(remoteData, success, xhr, handle) {
            var command = xhr.getResponseHeader('web2py-component-command');
            if (command == 'stop') handle.stop();
            el.button(remoteData.status).text(remoteData.text);
            bar.css('width', remoteData.perc);
            if(command) eval(decodeURIComponent(escape(command)));
        }
    )
})"""
    delete_button = request.controller == 'series' and request.function == 'index' and True or False
    if delete_button:
        delete_button = A(w2p_icon('delete', variant='white'), 'Delete Series', _href=URL(r=request, c='manage', f='delete', args=[request.args(0)]), _class="btn btn-large btn-danger")
    else:
        delete_button = ''

    return TAG[''](
        DIV(
               DIV(
                   DIV(_id="operation_progress", _class="bar", _style="width: 0%;"),
                   _class="progress progress-striped active"
                   ),
               DIV(
                   A(w2p_icon('Continuing', variant='white'),_id="operation_button", _href=URL('manage', 'stop_operations'), _class="btn btn-large btn-info",
                     _autocomplete="off", **{'_data-original-title' : 'background operations, click to stop them'}),
                   A(w2p_icon('add', variant='white'), 'Add Series', _href=URL(r=request, c='manage', f='add'), _class="btn btn-large btn-primary"),
                   delete_button,
                   _class="btn-group"
                   ),
            _class='well'),
        DIV(
            UL(
            LI("Genres", _class="nav-header"),
            LI(A('All', callback=URL(r=request, c='series', f='sidebar', args=request.args), target='series_sidebar', _class="nav nav-list")),
              [LI(
                  A(g, callback=URL(r=request, c='series', f='sidebar', args=request.args, vars={'genre': g}), target='series_sidebar',
                    _class="nav nav-list")
                  ) for g in genres],
              _class="nav nav-list"
              ),
            _class='well nopadding'
        ),
        DIV(
            UL(
            LI("Series", _class="nav-header"),
              [LI(
                  A(
                    w2p_icon(row.status),
                    row.name,
                    _href=URL(r=request, c='series', f='index', args=[row.id])),
                  _class = request.args(0) == str(row.id) and 'active' or None
                  ) for row in sidebar_series],
              _class="nav nav-list"
              ),
            _class='well nopadding'
        ),
            SCRIPT(script)
            )



def myrefurlwidget(urllist):
    """
    <div class="btn-group">
        <a class="btn dropdown-toggle" data-toggle="dropdown" href="#">
            Action
            <span class="caret"></span>
        </a>
    <ul class="dropdown-menu">
    <!-- dropdown menu links -->
    </ul>
    </div>
    """
    if not urllist:
        urllist = []
    lis = [LI(
             A(u, _href=u, _target="_blank")
             )
           for u in urllist]
    lis.append(LI(A("Settings", _href="#", _onclick="$('a[href=#series_settings]').tab('show');return false;")))
    rtn = DIV(
              A("Links", SPAN(_class="caret"), _href="#",_class="btn btn-info dropdown-toggle", **{'_data-toggle' : 'dropdown'}),
              UL(
                 lis
                 ,_class="dropdown-menu"),
              _class="btn-group")

    return rtn

def validate_seasons(seriesid):

    ep_tb = db.episodes
    se_tb = db.series
    settings = db.seasons_settings

    if not seriesid:
        base = (se_tb.id>0)
    else:
        base = (se_tb.id == seriesid)
    #insert a record for every season present
    seasons_to_insert = db(base & (ep_tb.seriesid == se_tb.seriesid)).select(se_tb.id, ep_tb.seasonnumber, distinct=True)

    for row in seasons_to_insert:
        settings.update_or_insert(
                                  (
                                   (settings.series_id == row.series.id) &
                                   (settings.seasonnumber == row.episodes.seasonnumber)
                                  ),
                                  series_id = row.series.id,
                                  seasonnumber = row.episodes.seasonnumber
                                  )


def twitter_widget(fi, form, style):
    rtn = []
    if fi == 'id':
        if form.custom.widget.id == '':
            return rtn
    if form.errors[fi]:
        groupclass = 'control-group error'
        comment = P(form.errors[fi], _class="help-block")
        if style == 'form-inline':
            comment['_class'] = 'help-inline'
        labelicon = w2p_icon('ko')
    else:
        groupclass = 'control-group'
        comment = ''
        labelicon = w2p_icon('ok')

    label = LABEL(
            "%s " % form.custom.label[fi],
        labelicon,
         _rel="tooltip",
        _class="control-label",
        _for="%s_%s" % (form.table, fi)
        ,**{'_data-original-title' : form.custom.comment[fi]}
    )

    if style == 'form-inline':
        rtn.append(
            TAG[''](
                label,
                form.custom.widget[fi],
                comment
            )
        )
    else:
        rtn.append(DIV(label,
                   DIV(form.custom.widget[fi],
                       comment,
                       _class="controls"),
                   _class=groupclass)
               )
    return rtn

def twitter_form(form, style="form-vertical"):
    rtn = []
    form['_class'] = style
    form.custom.begin = '<form class="%s" action="%s" enctype="%s" method="%s">' % (form['_class'], form['_action'],
                                                                                     form['_enctype'], form['_method'])
    rtn.append(XML(form.custom.begin))

    if not form.custom.submit.tag == 'div':
        form.custom.submit['_class'] = "btn btn-primary"

    try:
        wells = form.wells
    except:
        wells = [dict(title='',fields=form.fields)]

    fields_ = dict([(k, 1) for k in form.fields])

    for a in wells:
        well = []
        title, fields = a['title'], a['fields']
        well.append(H6(title))
        for fi in fields:
            wi = twitter_widget(fi, form, style)
            well.extend(wi)
            fields_.pop(fi)
        if not style == 'form-inline':
            well.append(HR())
        if not style == 'form-inline':
            rtn.append(DIV(well,_class="w2p_tvserieswell %s" % (title.lower().replace(' ', '_'))))
        else:
            rtn.append(TAG[''](well))

    if 'id' in fields_.keys():
        fields_.pop('id')

    if len(fields_.keys()) > 0:
        well = []
        for fi in fields_.keys():
            well.extend(twitter_widget(fi, form, style))

        rtn.append(DIV(well,_class="w2p_tvserieswell %s" % ('leftovers')))

    if style in ['form-inline']:
        rtn.append(form.custom.submit)
    else:
        rtn.append(DIV(form.custom.submit,_class="form-actions"))

    rtn.append(form.custom.end)

    return TAG[''](rtn)

def twitter_alert(alert, _class='alert alert-error'):

    return DIV(
        BUTTON(XML("&times;"), _class="close", **{'_data-dismiss' : 'alert'}),
        alert,
        _class=_class
    )


def get_season_path(series_id, seasonnumber):
    gs_tb = db.global_settings
    path_format = db(gs_tb.key == 'season_path').select(gs_tb.value).first()
    path_format = path_format and path_format.value or '%(seasonnumber).2d'

    #season_setting
    rec = db(
        (db.series.id == db.seasons_settings.series_id) &
        (db.seasons_settings.seasonnumber == seasonnumber) &
        (db.series.id == series_id) &
        (db.seasons_settings.tracking == True)
        ).select().first()

    if not rec:
        return None
    path = os.path.join(rec.series.basepath, path_format % dict(seasonnumber=seasonnumber))
    if os.path.exists(path):
        return path
    else:
        return None

def filenamelify(value):
    """taken from web2py's urlify"""
    s = value
    s = s.decode('utf-8')                 # to utf-8
    s = unicodedata.normalize('NFKD', s)  # normalize eg è => e, ñ => n
    s = s.encode('ASCII', 'ignore')       # encode as ASCII
    s = re.sub('&\w+;', '', s)            # strip html entities
    s = re.sub('[^\w\- ]', '', s)          # strip all but alphanumeric/underscore/hyphen/space
    s = re.sub('[-_][-_]+', '-', s)       # collapse strings of hyphens
    s = s.strip('-')                      # remove leading and trailing hyphens
    return s[:150]                        # 150 chars will be sufficient

def w2p_deposit(file):
    args = []
    filepart = DEPOSIT_RE.match(file)
    if filepart:
        args = list(filepart.groups())
    args.append(file)
    return URL('static', 'deposit', args=args, extension='')


def get_series_path(series_id):
    gs_tb = db.global_settings
    basefolder = db(gs_tb.key == 'series_basefolder').select(gs_tb.value).first()
    series = db.series(series_id)
    last = filenamelify(series.name)
    return os.path.join(basefolder.value, last, '').strip()


def twitter_menu(menu, level=0, mobile=False):
    """
    Generates twitter bootstrap's compliant menu
    """
    lis = []
    for li in menu:
        (text, active, href) = li[:3]
        sub =  len(li) > 3 and li[3] or []
        if len(sub) == 0:
            li_class = None
            el = LI(A(text, _href=href), _class=li_class)
            lis.append(el)
        else:
            li_class = 'dropdown'
            caret = level == 0 and B(_class='caret') or I(_class='icon-chevron-right')
            if mobile:
                li_class = None
                caret = B(_class='caret')
                sub_ul = twitter_menu(sub, level=level)
                el = LI(A(text, caret, _href=href, _class="dropdown-toggle", **{'_data-toggle' : 'dropdown'}), _class=li_class)
                lis.append(el)
                lis.extend(sub_ul)
            else:
                sub_ul = twitter_menu(sub, level=level+1)
                el = LI(A(text, caret, _href=href, _class="dropdown-toggle", **{'_data-toggle' : 'dropdown'}), sub_ul, _class=li_class)
                lis.append(el)
    if level == 0:
        return UL(*lis, _class='nav')
    else:
        if mobile:
            return lis
        return UL(*lis, _class="dropdown-menu")

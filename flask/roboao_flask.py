"""
    Flask-based server for the Robo-AO Data Archive

    Dr Dmitry A. Duev @ Caltech, 2016
"""

from __future__ import print_function
from gevent import monkey
monkey.patch_all()

import os
from pymongo import MongoClient
import json
import datetime
import ConfigParser
import argparse
import sys
import inspect
from collections import OrderedDict
import flask
import flask_login
from werkzeug.security import generate_password_hash, check_password_hash
from urlparse import urlparse
from astropy.coordinates import SkyCoord
from astropy import units
import pyvo as vo
from PIL import Image
import urllib2
from cStringIO import StringIO
from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas
import matplotlib.pyplot as plt
import numpy as np


def get_filter_code(_filter):
    # print(_filter)
    if _filter == 'Sloan g\'':
        return 'Sg'
    elif _filter == 'Sloan r\'':
        return 'Sr'
    elif _filter == 'Sloan i\'':
        return 'Si'
    elif _filter == 'Sloan z\'':
        return 'Sz'
    elif _filter == 'Longpass 600nm':
        return 'lp600'
    elif _filter == 'Clear':
        return 'c'
    elif _filter == 'H':
        return 'H'
    elif _filter == 'J':
        return 'J'
    else:
        raise Exception('couldn\'t recognize filter name')


def radec_str2rad(_ra_str, _dec_str):
    """

    :param _ra_str: 'H:M:S'
    :param _dec_str: 'D:M:S'
    :return: ra, dec in rad
    """
    # convert to rad:
    _ra = map(float, _ra_str.split(':'))
    _ra = (_ra[0] + _ra[1] / 60.0 + _ra[2] / 3600.0) * np.pi / 12.
    _dec = map(float, _dec_str.split(':'))
    _dec = (_dec[0] + _dec[1] / 60.0 + _dec[2] / 3600.0) * np.pi / 180.

    return _ra, _dec


def great_circle_distance(phi1, lambda1, phi2, lambda2):
    # input: dec1, ra1, dec2, ra2 [rad]
    # this is much faster than astropy.coordinates.Skycoord.separation
    delta_lambda = np.abs(lambda2 - lambda1)
    return np.arctan2(np.sqrt((np.cos(phi2)*np.sin(delta_lambda))**2
                              + (np.cos(phi1)*np.sin(phi2) - np.sin(phi1)*np.cos(phi2)*np.cos(delta_lambda))**2),
                      np.sin(phi1)*np.sin(phi2) + np.cos(phi1)*np.cos(phi2)*np.cos(delta_lambda))


def get_config(config_file='config.ini'):
    """
        load config data
    """
    try:
        abs_path = os.path.dirname(inspect.getfile(inspect.currentframe()))
        _config = ConfigParser.RawConfigParser()
        _config.read(os.path.join(abs_path, config_file))
        # logger.debug('Successfully read in the config file {:s}'.format(args.config_file))

        ''' connect to mongodb database '''
        conf = dict()
        # paths:
        conf['path_archive'] = _config.get('Path', 'path_archive')
        # database access:
        conf['mongo_host'] = _config.get('Database', 'host')
        conf['mongo_port'] = int(_config.get('Database', 'port'))
        conf['mongo_db'] = _config.get('Database', 'db')
        conf['mongo_collection_obs'] = _config.get('Database', 'collection_obs')
        conf['mongo_collection_aux'] = _config.get('Database', 'collection_aux')
        conf['mongo_collection_pwd'] = _config.get('Database', 'collection_pwd')
        conf['mongo_collection_weather'] = _config.get('Database', 'collection_weather')
        conf['mongo_user'] = _config.get('Database', 'user')
        conf['mongo_pwd'] = _config.get('Database', 'pwd')

        ''' server location '''
        conf['server_host'] = _config.get('Server', 'host')
        conf['server_port'] = _config.get('Server', 'port')

        # VO server:
        conf['vo_server'] = _config.get('Misc', 'vo_url')

        return conf

    except Exception as _e:
        print(_e)
        raise Exception('Failed to read in the config file')


def parse_obs_name(_obs, _program_pi):
    """
        Parse Robo-AO observation name
    :param _obs:
    :param _program_pi: dict program_num -> PI
    :return:
    """
    # parse name:
    _tmp = _obs.split('_')
    # program num. it will be a string in the future
    _prog_num = str(_tmp[0])
    # who's pi?
    if _prog_num in _program_pi.keys():
        _prog_pi = _program_pi[_prog_num]
    else:
        # play safe if pi's unknown:
        _prog_pi = 'admin'
    # stack name together if necessary (if contains underscores):
    _sou_name = '_'.join(_tmp[1:-5])
    # code of the filter used:
    _filt = _tmp[-4:-3][0]
    # date and time of obs:
    _date_utc = datetime.datetime.strptime(_tmp[-2] + _tmp[-1], '%Y%m%d%H%M%S.%f')
    # camera:
    _camera = _tmp[-5:-4][0]
    # marker:
    _marker = _tmp[-3:-2][0]

    return _prog_num, _prog_pi, _sou_name, _filt, _date_utc, _camera, _marker


def connect_to_db(_config):
    """ Connect to the mongodb database

    :return:
    """
    try:
        _client = MongoClient(host=_config['mongo_host'], port=_config['mongo_port'])
        _db = _client[_config['mongo_db']]
    except Exception as _e:
        print(_e)
        _db = None
    try:
        _db.authenticate(_config['mongo_user'], _config['mongo_pwd'])
    except Exception as _e:
        print(_e)
        _db = None
    try:
        _coll = _db[_config['mongo_collection_obs']]
    except Exception as _e:
        print(_e)
        _coll = None
    try:
        _coll_aux = _db[_config['mongo_collection_aux']]
    except Exception as _e:
        print(_e)
        _coll_aux = None
    try:
        _coll_weather = _db[_config['mongo_collection_weather']]
    except Exception as _e:
        print(_e)
        _coll_weather = None
    try:
        _coll_usr = _db[_config['mongo_collection_pwd']]
    except Exception as _e:
        print(_e)
        _coll_usr = None
    try:
        # build dictionary program num -> pi username
        cursor = _coll_usr.find()
        _program_pi = {}
        for doc in cursor:
            # handle admin separately
            if doc['_id'] == 'admin':
                continue
            _progs = doc['programs']
            for v in _progs:
                _program_pi[str(v)] = doc['_id'].encode('ascii', 'ignore')
                # print(program_pi)
    except Exception as _e:
        print(_e)
        _program_pi = None

    return _client, _db, _coll, _coll_usr, _coll_aux, _coll_weather, _program_pi


# import functools
# def background(f):
#     @functools.wraps(f)
#     def wrapper(*args, **kwargs):
#         jobid = uuid4().hex
#         key = 'job-{0}'.format(jobid)
#         skey = 'job-{0}-status'.format(jobid)
#         expire_time = 3600
#         redis.set(skey, 202)
#         redis.expire(skey, expire_time)
#
#         @copy_current_request_context
#         def task():
#             try:
#                 data = f(*args, **kwargs)
#             except:
#                 redis.set(skey, 500)
#             else:
#                 redis.set(skey, 200)
#                 redis.set(key, data)
#                 redis.expire(key, expire_time)
#             redis.expire(skey, expire_time)
#
#         gevent.spawn(task)
#         return jsonify({"job": jobid})
#     return wrapper

''' initialize the Flask app '''
app = flask.Flask(__name__)
app.secret_key = 'roboaokicksass'
# add 'do' statement to jinja environment (does the same as {{ }}, but return nothing):
app.jinja_env.add_extension('jinja2.ext.do')


def get_db(_config):
    """Opens a new database connection if there is none yet for the
    current application context.
    """
    if not hasattr(flask.g, 'client'):
        flask.g.client, flask.g.db, flask.g.coll, flask.g.coll_usr, \
        flask.g.coll_aux, flask.g.coll_weather, flask.g.program_pi = connect_to_db(_config)
    return flask.g.client, flask.g.db, flask.g.coll, flask.g.coll_usr, \
                flask.g.coll_aux, flask.g.coll_weather, flask.g.program_pi


@app.teardown_appcontext
def close_db(error):
    """Closes the database again at the end of the request."""
    if hasattr(flask.g, 'client'):
        flask.g.client.close()


login_manager = flask_login.LoginManager()

login_manager.init_app(app)


''' Create command line argument parser '''
parser = argparse.ArgumentParser(formatter_class=argparse.RawDescriptionHelpFormatter,
                                 description='Data archive for Robo-AO')

parser.add_argument('config_file', metavar='config_file',
                    action='store', help='path to config file.', type=str)

args = parser.parse_args()
config_file = args.config_file


''' get config data '''
try:
    config = get_config(config_file=config_file)
except IOError:
    config = get_config(config_file='config.ini')
# print(config)

''' serve additional static data (preview images, compressed source data)

When deploying, make sure WSGIScriptAlias is overridden by Apache's directive:

Alias "/data/" "/path/to/archive/data"
<Directory "/path/to/app/static/">
  Order allow,deny
  Allow from all
</Directory>

Check details at:
http://stackoverflow.com/questions/31298755/how-to-get-apache-to-serve-static-files-on-flask-webapp

Once deployed, comment the following definition:
'''


# FIXME:
@app.route('/data/<path:filename>')
def data_static(filename):
    """
        Get files from the archive
    :param filename:
    :return:
    """
    _p, _f = os.path.split(filename)
    return flask.send_from_directory(os.path.join(config['path_archive'], _p), _f)


''' handle user login'''


class User(flask_login.UserMixin):
    pass


@login_manager.user_loader
def user_loader(username):
    # look up username in database:
    client, db, coll, coll_usr, coll_aux, coll_weather, program_pi = get_db(config)
    select = coll_usr.find_one({'_id': username})
    if select is None:
        return

    user = User()
    user.id = username
    return user


@login_manager.request_loader
def request_loader(request):
    username = request.form.get('username')
    client, db, coll, coll_usr, coll_aux, coll_weather, program_pi = get_db(config)
    # look up in the database
    select = coll_usr.find_one({'_id': username})
    if select is None:
        return

    user = User()
    user.id = username

    try:
        user.is_authenticated = check_password_hash(select['password'],
                                                    flask.request.form['password'])
    except Exception as _e:
        print(_e)
        return

    return user


@app.route('/login', methods=['GET', 'POST'])
def login():
    if flask.request.method == 'GET':
        # logged in already?
        if flask_login.current_user.is_authenticated:
            return flask.redirect(flask.url_for('root'))
        # serve template if not:
        else:
            return flask.render_template('template-login.html', fail=False)
    # print(flask.request.form['username'], flask.request.form['password'])

    username = flask.request.form['username']
    # check if username exists and passwords match
    # look up in the database first:
    client, db, coll, coll_usr, coll_aux, coll_weather, program_pi = get_db(config)
    select = coll_usr.find_one({'_id': username})
    if select is not None and \
            check_password_hash(select['password'], flask.request.form['password']):
        user = User()
        user.id = username
        flask_login.login_user(user, remember=True)
        return flask.redirect(flask.url_for('root'))
    else:
        # serve template with flag fail=True to display fail message
        return flask.render_template('template-login.html', fail=True)


def stream_template(template_name, **context):
    """
        see: http://flask.pocoo.org/docs/0.11/patterns/streaming/
    :param template_name:
    :param context:
    :return:
    """
    app.update_template_context(context)
    t = app.jinja_env.get_template(template_name)
    rv = t.stream(context)
    rv.enable_buffering(5)
    return rv


def get_dates(user_id, coll, coll_aux, start=None, stop=None):
    """
        Get science and auxiliary data from start to stop
    :param user_id:
    :param coll:
    :param coll_aux:
    :param start:
    :param stop:
    :return:
    """
    if start is None:
        # this is ~when we moved to KP:
        # start = datetime.datetime(2015, 10, 1)
        # by default -- last 30 days:
        start = datetime.datetime.utcnow() - datetime.timedelta(days=10)
    else:
        try:
            start = datetime.datetime.strptime(start, '%Y%m%d')
        except Exception as _e:
            print(_e)
            start = datetime.datetime.utcnow() - datetime.timedelta(days=10)

    if stop is None:
        stop = datetime.datetime.utcnow()
    else:
        try:
            stop = datetime.datetime.strptime(stop, '%Y%m%d')
            # if stop < start:
            #     stop = datetime.datetime.utcnow()
        except Exception as _e:
            print(_e)
            stop = datetime.datetime.utcnow()

    # create indeces not to perform in-memory sorting:
    coll.create_index([('date_utc', -1)])
    coll_aux.create_index([('_id', -1)])

    # dictionary: {date: {data: {program_N: [observations]}, aux: {}}}
    dates = dict()

    if user_id == 'admin':
        # get everything;
        cursor = coll.find({'date_utc': {'$gte': start, '$lt': stop}})
    else:
        # get only programs accessible to this user marked as distributed:
        cursor = coll.find({'date_utc': {'$gte': start, '$lt': stop},
                            'science_program.program_PI': user_id,
                            'distributed.status': True})

    # iterate over query result for science data:
    try:
        for obs in cursor.sort([('date_utc', -1)]):
            date = obs['date_utc'].strftime('%Y%m%d')
            # add key to dict if it is not there already:
            if date not in dates:
                dates[date] = {'data': {}, 'aux': {}}
            # add key for program if it is not there yet
            program_id = obs['science_program']['program_id']
            if program_id not in dates[date]['data']:
                dates[date]['data'][program_id] = []
            dates[date]['data'][program_id].append(obs)
    except Exception as _e:
        print(_e)

    # get aux data
    cursor_aux = coll_aux.find({'_id': {'$gte': start.strftime('%Y%m%d'), '$lt': stop.strftime('%Y%m%d')}})

    # iterate over query result for aux data:
    try:
        for date_data in cursor_aux:
            # string date
            date = date_data['_id']

            aux = OrderedDict()

            for key in ('seeing', 'contrast_curve', 'strehl'):
                if key in date_data and date_data[key]['done']:
                    aux[key] = dict()
                    aux[key]['done'] = True if (key in date_data and date_data[key]['done']) else False
                    if key == 'seeing':
                        # for seeing data, fetch frame names to show in a 'movie'
                        aux[key]['frames'] = []
                        # sort by time, not by name:
                        ind_sort = np.argsort([frame[1] for frame in date_data[key]['frames']])
                        for frame in np.array(date_data[key]['frames'])[ind_sort]:
                            aux[key]['frames'].append(frame[0] + '.png')

            if len(aux) > 0:
                # show aux data for the admin all the time
                if user_id == 'admin':
                    # init entry if no science
                    if date not in dates:
                        dates[date] = {'data': {}, 'aux': {}}
                    # add to dates:
                    dates[date]['aux'] = aux
                # for regular users, only show aux data for dates with obs of user's programs
                else:
                    if date in dates:
                        dates[date]['aux'] = aux
    except Exception as _e:
        print(_e)

    # print(dates)
    # latest obs - first
    # dates = sorted(list(set(dates)), reverse=True)

    return dates


@app.route('/_get_fits_header')
@flask_login.login_required
def get_fits_header():
    """
        Get FITS header for a _source_ observed on a _date_
    :return: jsonified dictionary with the header / empty dict if failed
    """
    user_id = flask_login.current_user.id

    # get parameters from the AJAX GET request
    _obs = flask.request.args.get('source', 0, type=str)

    _, _, coll, _, _, _, _program_pi = get_db(config)

    # trying to steal stuff?
    _program, _, _, _, _, _, _ = parse_obs_name(_obs, _program_pi)
    if user_id != 'admin' and _program_pi[_program] != user_id:
        # flask.abort(403)
        return flask.jsonify(result={})

    cursor = coll.find({'_id': _obs})

    try:
        if cursor.count() == 1:
            for obs in cursor:
                header = obs['pipelined']['automated']['fits_header']
            return flask.jsonify(result=OrderedDict(header))
        # not found in the database?
        else:
            return flask.jsonify(result={})
    except Exception as _e:
        print(_e)
        return flask.jsonify(result={})


@app.route('/_get_vo_image', methods=['GET'])
@flask_login.login_required
def get_vo_image():
    user_id = flask_login.current_user.id

    # get parameters from the AJAX GET request
    _obs = flask.request.args.get('source', 0, type=str)

    _, _, coll, _, _, _, _program_pi = get_db(config)

    # trying to steal stuff?
    _program, _, _, _, _, _, _ = parse_obs_name(_obs, _program_pi)
    if user_id != 'admin' and _program_pi[_program] != user_id:
        # flask.abort(403)
        return flask.jsonify(result={})

    # print(_obs)
    cursor = coll.find({'_id': _obs})

    try:
        if cursor.count() == 1:
            for obs in cursor:
                header = obs['pipelined']['automated']['fits_header']
                if 'TELDEC' in header and 'TELRA' in header:
                    c = SkyCoord(header['TELRA'][0], header['TELDEC'][0],
                                 unit=(units.hourangle, units.deg), frame='icrs')
                    # print(c)
                    # print(c.ra.deg, c.dec.deg)

                    vo_url = config['vo_server']

                    survey_filter = {'dss2': 'r', '2mass': 'h'}
                    output = {}

                    for survey in survey_filter:

                        # TODO: use image size + scale from config. For now it's 36"x36" times 2 (0.02 deg^2)
                        previews = vo.imagesearch(vo_url, pos=(c.ra.deg, c.dec.deg),
                                                  size=(0.01*2, 0.01*2), format='image/png',
                                                  survey=survey)
                        if previews.nrecs == 0:
                            continue
                        # get url:
                        image_url = [image.getdataurl() for image in previews
                                     if image.title == survey + survey_filter[survey]][0]

                        _file = StringIO(urllib2.urlopen(image_url).read())
                        survey_image = np.array(Image.open(_file))

                        fig = plt.figure(figsize=(3, 3))
                        ax = fig.add_subplot(111)
                        ax.imshow(survey_image, origin='upper', interpolation='nearest', cmap=plt.cm.magma)
                        ax.grid('off')
                        ax.set_axis_off()
                        fig.subplots_adjust(wspace=0, hspace=0, top=1, bottom=0, right=1, left=0)
                        plt.margins(0, 0)
                        # flip x axis for it to look like our images:
                        plt.gca().invert_xaxis()
                        plt.gca().invert_yaxis()

                        canvas = FigureCanvas(fig)
                        png_output = StringIO()
                        canvas.print_png(png_output)
                        png_output = png_output.getvalue().encode('base64')

                        output['{:s}_{:s}'.format(survey, survey_filter[survey])] = png_output

            return flask.jsonify(result=output)
        # not found in the database?
        else:
            return flask.jsonify(result={})
    except Exception as _e:
        print(_e)
        return flask.jsonify(result={})


@app.route('/get_data', methods=['GET'])
@flask_login.login_required
def wget_script():
    """
        Generate bash script to fetch all data for date/program with wget
    :return:
    """
    url = urlparse(flask.request.url).netloc
    _date_str = flask.request.args['date']
    _date = datetime.datetime.strptime(_date_str, '%Y%m%d')
    _program = flask.request.args['program']

    user_id = flask_login.current_user.id
    # get db connection
    client, db, coll, coll_usr, coll_aux, coll_weather, program_pi = get_db(config)

    # trying to get something you're not supposed to get?
    if user_id != 'admin' and program_pi[_program] != user_id:
        flask.abort(403)
    else:
        cursor = coll.find({'date_utc': {'$gte': _date,
                                         '$lt': _date + datetime.timedelta(days=1)},
                            'science_program.program_id': _program,
                            'distributed.status': True})
        response_text = '#!/usr/bin/env bash\n'
        for obs in cursor:
            response_text += 'wget http://{:s}/data/{:s}/{:s}/{:s}.tar.bz2\n'.format(url, _date_str,
                                                                                obs['_id'], obs['_id'])
        # print(response_text)

        # generate .sh file on the fly
        response = flask.make_response(response_text)
        response.headers['Content-Disposition'] = \
            'attachment; filename=program_{:s}_{:s}.wget.sh'.format(_program, _date_str)
        return response


# serve root
@app.route('/', methods=['GET'])
@flask_login.login_required
def root():

    if 'start' in flask.request.args:
        start = flask.request.args['start']
    else:
        start = None
    if 'stop' in flask.request.args:
        stop = flask.request.args['stop']
    else:
        stop = None

    user_id = flask_login.current_user.id

    def iter_dates(_dates):
        """
            instead of first loading and then sending everything to user all at once,
             yield data for a single date at a time and stream to user
        :param _dates:
        :return:
        """
        if len(_dates) > 0:
            for _date in sorted(_dates.keys())[::-1]:
                # print(_date, _dates[_date])
                yield _date, _dates[_date]['data'], _dates[_date]['aux']
        else:
            yield None, None, None

    # get db connection
    client, db, coll, coll_usr, coll_aux, coll_weather, program_pi = get_db(config)

    # get science and aux data for all dates:
    dates = get_dates(user_id, coll, coll_aux, start=start, stop=stop)

    return flask.Response(stream_template('template-archive.html',
                                          user=user_id, start=start, stop=stop,
                                          dates=iter_dates(dates)))


# serve root
@app.route('/search', methods=['GET', 'POST'])
@flask_login.login_required
def search():
    """

    :return:
    """
    user_id = flask_login.current_user.id

    # get db connection
    client, db, coll, coll_usr, coll_aux, coll_weather, program_pi = get_db(config)

    # program numbers available for searching:
    # if user_id != 'admin' and _program_pi[_program] != user_id:
    if user_id == 'admin':
        program_ids = program_pi.keys() if len(program_pi.keys()) > 0 else []
    else:
        program_ids = [program_id for program_id in program_pi.keys() if program_pi[program_id] == user_id]

    # got a request?
    if flask.request.method == 'POST':
        # print(flask.request.form)
        # create indices before searching:
        coll.drop_indexes()
        # coll.create_index([('name', 1)])
        coll.create_index([('coordinates.radec_geojson', '2dsphere'), ('name', 1)])

        # query db
        obs, errors = query_db(search_form=flask.request.form, _coll=coll, _program_ids=program_ids, _user_id=user_id)
    else:
        obs = dict()
        errors = []

    return flask.Response(stream_template('template-search.html', form=flask.request.form,
                                          user=user_id, program_ids=program_ids, obs=obs, errors=errors))


def query_db(search_form, _coll, _program_ids, _user_id):
    """
        parse search form and generate db query
    :param search_form:
    :return:
    """
    # dict to store query to be executed:
    query = dict()
    # list to store the results:
    obs = []
    # list to store errors
    errors = []

    # source name
    source_name = search_form['source_name'].strip()
    # print(source_name)
    source_name_exact = True if ('source_name_exact' in search_form) and search_form['source_name_exact'] == 'on' \
        else False
    if len(source_name) > 0:
        if source_name_exact:
            # exact:
            query['name'] = source_name
            # select = _coll.find({'name': source_name})
        else:
            # contains:
            query['name'] = {'$regex': u'.*{:s}.*'.format(source_name)}
            # select = _coll.find({'name': {'$regex': u'.*{:s}.*'.format(source_name)}})

    # program id:
    program_id = search_form['program_id']
    # security check for non-admin users:
    if _user_id != 'admin' and program_id != 'all':
        assert program_id in _program_ids, \
            'user {:s} tried accessing info that does not belong to him!'.format(_user_id)
    # strict check:
    if program_id == 'all':
        if _user_id != 'admin':
            query['science_program.program_id'] = {'$in': _program_ids}
    else:
        query['science_program.program_id'] = program_id

    # time range:
    try:
        date_range = search_form['daterange'].split('-')
        date_from = date_range[0].strip()
        date_from = datetime.datetime.strptime(date_from, '%Y/%m/%d %H:%M')

        date_to = date_range[1].strip()
        date_to = datetime.datetime.strptime(date_to, '%Y/%m/%d %H:%M')
        query['date_utc'] = {'$gte': date_from, '$lt': date_to}
    except Exception as _e:
        print(_e)
        errors.append('Failed to parse date range')
        return {}, errors

    # position
    ra_str = search_form['ra'].strip()
    dec_str = search_form['dec'].strip()
    if len(ra_str) > 0 and len(dec_str) > 0:
        try:
            # try to guess format and convert to decimal degrees:

            # hms -> ::, dms -> ::
            if ('h' in ra_str) and ('m' in ra_str) and ('s' in ra_str):
                ra_str = ra_str[:-1]  # strip 's' at the end
                for char in ('h', 'm'):
                    ra_str.replace(char, ':')
            if ('d' in dec_str) and ('m' in dec_str) and ('s' in dec_str):
                dec_str = dec_str[:-1]  # strip 's' at the end
                for char in ('d', 'm'):
                    dec_str.replace(char, ':')

            if (':' in ra_str) and (':' in dec_str):
                ra, dec = radec_str2rad(ra_str, dec_str)
            else:
                # already in radian?
                ra = float(ra_str)
                dec = float(dec_str)

            # do cone search
            if 'cone_search_radius' in search_form:
                if len(search_form['cone_search_radius'].strip()) > 0:
                    cone_search_radius = float(search_form['cone_search_radius'])
                    # convert to rad:
                    if search_form['cone_search_unit'] == 'arcsec':
                        cone_search_radius *= np.pi/180.0/3600.
                    elif search_form['cone_search_unit'] == 'arcmin':
                        cone_search_radius *= np.pi/180.0/60.
                    elif search_form['cone_search_unit'] == 'deg':
                        cone_search_radius *= np.pi/180.0

                    # ra, dec in geospatial-friendly format:
                    ra *= 180.0 / np.pi
                    ra -= 180.0
                    dec *= 180.0 / np.pi

                    # print(ra_str, dec_str)
                    # print(ra, dec)
                    # print(cone_search_radius)

                    query['coordinates.radec_geojson'] = {'$geoWithin': {'$centerSphere': [[ra, dec],
                                                                                           cone_search_radius]}}

                else:
                    errors.append('Must specify cone search radius')
                    return {}, errors
            else:
                # (almost) exact match wanted instead?
                pass

        except Exception as _e:
            print(_e)
            errors.append('Failed to recognize RA/Dec format')
            return {}, errors

    # source id
    source_id = search_form['source_id'].strip()
    source_id_exact = True if ('source_id_exact' in search_form) and search_form['source_id_exact'] == 'on' else False
    if len(source_id) > 0:
        if source_id_exact:
            # exact:
            query['_id'] = source_id
        else:
            # contains:
            query['_id'] = {'$regex': u'.*{:s}.*'.format(source_id)}

    # filter:
    filt = search_form['filter']
    if filt != 'any':
        try:
            query['filter'] = get_filter_code(_filter=filt)
        except Exception as e:
            print(e)

    # parse sliders:
    for key in ('magnitude', 'exposure', 'azimuth', 'elevation', 'lucky_strehl', 'faint_strehl'):
        try:
            val = search_form[key]
            if len(val) > 0:
                rng = map(float, val.split(','))
                assert rng[0] <= rng[1], 'invalid range for {:s}'.format(key)
                if key == 'azimuth':
                    if rng == [0.0, 360.0]:
                        continue
                    rng[0] *= np.pi / 180.0
                    rng[1] *= np.pi / 180.0
                    key_query = 'coordinates.azel.0'
                elif key == 'elevation':
                    if rng == [0.0, 90.0]:
                        continue
                    rng[0] *= np.pi / 180.0
                    rng[1] *= np.pi / 180.0
                    key_query = 'coordinates.azel.1'
                elif key == 'lucky_strehl':
                    if rng == [0.0, 100.0]:
                        continue
                    key_query = 'pipelined.automated.strehl.ratio_percent'
                elif key == 'faint_strehl':
                    if rng == [0.0, 100.0]:
                        continue
                    key_query = 'pipelined.faint.strehl.ratio_percent'
                elif key == 'seeing':
                    if rng == [0.1, 3.0]:
                        continue
                    key_query = 'seeing.nearest'
                elif key == 'magnitude':
                    if rng == [-6.0, 23.0]:
                        continue
                    key_query = 'magnitude'
                elif key == 'exposure':
                    if rng == [0.0, 600.0]:
                        continue
                    key_query = 'magnitude'
                else:
                    key_query = key
                # add to query
                # print(key_query, rng)
                query[key_query] = {'$gte': rng[0], '$lte': rng[1]}
        except Exception as e:
            print(e)
            continue

    # execute query:
    if len(query) > 0:
        # print('executing query:\n{:s}'.format(query))
        select = _coll.find(query)

        for ob in select:
            # print('matching:', ob['_id'])
            # don't transfer everything -- too much stuff, filter out
            ob_out = dict()
            for key in ('_id', 'seeing', 'science_program', 'name', 'exposure', 'camera', 'magnitude',
                        'filter', 'date_utc', 'coordinates', 'distributed'):
                ob_out[key] = ob[key]
            ob_out['pipelined'] = dict()
            for key in ('automated', 'faint'):
                ob_out['pipelined'][key] = dict()
                ob_out['pipelined'][key]['status'] = ob['pipelined'][key]['status']
                ob_out['pipelined'][key]['preview'] = ob['pipelined'][key]['preview']
                ob_out['pipelined'][key]['strehl'] = ob['pipelined'][key]['strehl']
                ob_out['pipelined'][key]['pca'] = dict()
                ob_out['pipelined'][key]['pca']['status'] = ob['pipelined'][key]['pca']['status']
                ob_out['pipelined'][key]['pca']['preview'] = ob['pipelined'][key]['pca']['preview']

            # append to output dict
            obs.append(ob_out)

    return obs, errors


# manage users
@app.route('/manage_users')
@flask_login.login_required
def manage_users():
    if flask_login.current_user.id == 'admin':
        # fetch users from the database:
        _users = {}
        client, db, coll, coll_usr, coll_aux, coll_weather, program_pi = get_db(config)
        cursor = coll_usr.find()
        for usr in cursor:
            # print(usr)
            if usr['programs'] == 'all':
                _users[usr['_id']] = {'programs': ['all']}
            else:
                _users[usr['_id']] = {'programs': [p.encode('ascii', 'ignore')
                                                   for p in usr['programs']]}

        return flask.render_template('template-users.html',
                                     user=flask_login.current_user.id,
                                     users=_users)
    else:
        flask.abort(403)


@app.route('/add_user', methods=['GET'])
@flask_login.login_required
def add_user():
    try:
        user = flask.request.args['user']
        password = flask.request.args['password']
        programs = [p.strip().encode('ascii', 'ignore')
                    for p in flask.request.args['programs'].split(',')]
        # print(user, password, programs)
        # print(len(user), len(password), len(programs))
        if len(user) == 0 or len(password) == 0:
            return 'everything must be set'
        client, db, coll, coll_usr, coll_aux, coll_weather, program_pi = get_db(config)
        # add user to coll_usr collection:
        coll_usr.insert_one(
            {'_id': user,
             'password': generate_password_hash(password),
             'programs': programs,
             'last_modified': datetime.datetime.now()}
        )
        # change data ownership in the main database:
        if user != 'admin':  # admin has it 'all'!
            coll.update({'science_program.program_id': {'$in': programs}},
                        {'$set': {'science_program.program_PI': user}}, multi=True)

        return 'success'
    except Exception as _e:
        print(_e)
        return _e


@app.route('/edit_user', methods=['GET'])
@flask_login.login_required
def edit_user():
    try:
        # print(flask.request.args)
        id = flask.request.args['_user']
        if id == 'admin':
            return 'Cannot remove the admin!'
        user = flask.request.args['edit-user']
        password = flask.request.args['edit-password']
        programs = [p.strip().encode('ascii', 'ignore')
                    for p in flask.request.args['edit-programs'].split(',')]
        # print(user, password, programs, id)
        # print(len(user), len(password), len(programs))
        if len(user) == 0:
            return 'username must be set'
        # keep old password:
        if len(password) == 0:
            client, db, coll, coll_usr, coll_aux, coll_weather, program_pi = get_db(config)
            result = coll_usr.update_one(
                {'_id': id},
                {
                    '$set': {
                        '_id': user,
                        'programs': programs
                    },
                    '$currentDate': {'last_modified': True}
                }
            )
        # else change password too:
        else:
            client, db, coll, coll_usr, coll_aux, coll_weather, program_pi = get_db(config)
            result = coll_usr.update_one(
                {'_id': id},
                {
                    '$set': {
                        '_id': user,
                        'password': generate_password_hash(password),
                        'programs': programs
                    },
                    '$currentDate': {'last_modified': True}
                }
            )

        # change program ownership if necessary:
        # get all program numbers for this user:
        programs_in_db = [k for k in program_pi.keys() if program_pi[k] == user]
        old_set = set(programs_in_db)
        new_set = set(programs)
        # change data ownership in the main database:
        if user != 'admin':  # admin has it 'all'!
            # added new programs?
            if len(new_set - old_set) > 0:
                # reset ownership for the set difference new-old (program in new, but not in old)
                coll.update({'science_program.program_id': {'$in': list(new_set - old_set)}},
                            {'$set': {'science_program.program_PI': user}}, multi=True)
            # removed programs? reset ownership to admin
            if len(old_set - new_set) > 0:
                # reset ownership for the set difference old-new (program in old, but not in new)
                coll.update({'science_program.program_id': {'$in': list(old_set - new_set)}},
                            {'$set': {'science_program.program_PI': 'admin'}}, multi=True)
        return 'success'
    except Exception as _e:
        print(_e)
        return _e


@app.route('/remove_user', methods=['GET', 'POST'])
@flask_login.login_required
def remove_user():
    try:
        # print(flask.request.args)
        # get username from request
        user = flask.request.args['user']
        if user == 'admin':
            return 'Cannot remove the admin!'
        # print(user)

        # get db:
        client, db, coll, coll_usr, coll_aux, coll_weather, program_pi = get_db(config)
        # get all program numbers for this user:
        user_programs = [k for k in program_pi.keys() if program_pi[k] == user]
        # try to remove the user:
        coll_usr.delete_one({'_id': user})
        # change data ownership to 'admin'
        coll.update({'science_program.program_id': {'$in': user_programs}},
                    {'$set': {'science_program.program_PI': 'admin'}}, multi=True)

        return 'success'
    except Exception as _e:
        print(_e)
        return _e


@app.route('/logout', methods=['GET', 'POST'])
def logout():
    flask_login.logout_user()
    return flask.redirect(flask.url_for('root'))


@app.errorhandler(500)
def internal_error(error):
    return '500 error'


@app.errorhandler(404)
def not_found(error):
    return '404 error'


@app.errorhandler(403)
def not_found(error):
    return '403 error: forbidden'


@login_manager.unauthorized_handler
def unauthorized_handler():
    return flask.redirect(flask.url_for('login'))


if __name__ == '__main__':
    app.run(host=config['server_host'], port=config['server_port'], threaded=True)
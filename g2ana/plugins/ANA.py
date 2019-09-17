#
# ANA.py -- ANA plugin for Ginga FITS viewer
#
# Takeshi Inagaki
# Eric Jeschke (eric@naoj.org)
#
import os, pwd
import fcntl
import select
import re, time
import errno

from ginga import GingaPlugin
from ginga import AstroImage
from ginga.util import wcs, loader, paths

# g2cam imports
from g2base.remoteObjects import remoteObjects as ro
from g2base.remoteObjects import Monitor

from g2base.astro.frame import Frame
import g2cam.INS as INSconfig

homedir = paths.home
propid_file = os.path.join(homedir, '.ana_propid')

class AnaError(Exception):
    pass

class ANA(GingaPlugin.GlobalPlugin):
    """
    NOTE: *** All these methods are running as the GUI thread, unless
    otherwise noted. Do not block!! ***
    """

    def __init__(self, fv):
        # superclass defines some variables for us, like logger
        super(ANA, self).__init__(fv)

        # Find out what proposal ID we are logged in under
        self.propid = None
        username = pwd.getpwuid(os.getuid()).pw_name
        match = re.match(r'^[uo](\d{5})$', username)
        if match:
            self.propid = 'o' + match.group(1)
        else:
            if os.path.exists(propid_file):
                try:
                    with open(propid_file, 'r') as in_f:
                        self.propid = in_f.read().strip()
                except Exception:
                    pass
        if self.propid is None:
            raise AnaError("Unable to determine prop-id for ANA operation")
        match = re.match(r'^o(\d{5})$', self.propid)
        if not match:
            raise AnaError("PROP-ID ({}) doesn't match expected format (oNNMMM)")

        # find out our hostname
        self.host = ro.get_myhost(short=True)
        self.ro_host = 'g2ins1.sum.subaru.nao.ac.jp'

        ro.init([self.ro_host])

        # construct our service name
        self.svcname = "ANA-{}-{}".format(self.propid, self.host)

        # for looking up instrument names
        self.insconfig = INSconfig.INSdata()

        self.fifo_name = None
        self.fifo_fd = None
        self.fifo_sleep = 0.5

        # make a name and port for our monitor
        mymonname = '{}.mon'.format(self.svcname)
        self.monport = 10000 + int(self.propid[-3:])
        self.port = 9000 + int(self.propid[-3:])
        #self.channels = ['g2task']

        threadPool = self.fv.get_threadPool()

        # Create a local pub sub instance
        self.monitor = Monitor.Monitor(mymonname, self.logger,
                                       threadPool=threadPool,
                                       ev_quit=self.fv.ev_quit)

        # some of the other plugins expect this handle to be available
        # via fv
        self.fv.controller = self

    def start(self):
        self.logger.info("starting ANA plugin for propid: {}".format(self.propid))

        # Startup monitor threadpool
        self.monitor.start(wait=True)

        # start_server is necessary if we are subscribing, but not if only
        # publishing
        #self.logger.info("starting monitor on port {}".format(self.monport))
        #self.monitor.start_server(wait=True, port=self.monport)

        # subscribe our monitor to the central monitor hub
        #self.monitor.subscribe_remote(self.monitor_name, self.channels, {})
        # publishing for remote command executions
        self.monitor.publish_to('monitor', ['g2task'], {})

        # Create our remote service object
        threadPool = self.fv.get_threadPool()
        # methods that can be called from outside via our service
        method_list = ['callGlobalPlugin2']
        self.viewsvc = ro.remoteObjectServer(svcname=self.svcname,
                                             obj=self,
                                             logger=self.logger,
                                             ev_quit=self.fv.ev_quit,
                                             port=self.port,
                                             usethread=True,
                                             threadPool=threadPool,
                                             method_list=method_list)

        self.logger.info("starting ANA service on port {}".format(self.port))
        self.viewsvc.ro_start()

        self.logger.info("making FIFO..")
        self.fifo_path = os.path.join('/tmp', ".fits_" + self.propid + "_fifo")
        if not os.path.exists(self.fifo_path):
            os.mkfifo(self.fifo_path, 0o777)
        os.system("chmod o+w {}".format(self.fifo_path))

        self.fifo_fd = os.open(self.fifo_path, os.O_RDONLY | os.O_NONBLOCK)
        self.logger.info("made fifo ({})".format(self.fifo_path))

        self.fv.nongui_do(self._load_files, self.fv.ev_quit)
        self.logger.info("ANA plugin started.")

    def stop(self):
        self.logger.info("ANA plugin shutting down...")
        self.viewsvc.ro_stop(wait=True)
        self.monitor.stop_server(wait=True)
        self.monitor.stop(wait=True)

        os.close(self.fifo_fd)
        if self.propid is not None:
            os.remove(self.fifo_path)

        self.logger.info("ANA plugin stopped.")

    def _load_files(self, ev_quit):

        self.logger.info("starting load_files()..")
        bufsize = 1024

        while not ev_quit.is_set():
            self.logger.debug("pinging fifo...")
            buf = None
            try:
                buf = os.read(self.fifo_fd, bufsize)

            except OSError as err:
                if err.errno == errno.EAGAIN or err.errno == errno.EWOULDBLOCK:
                    pass
                else:
                    raise

            self.logger.debug("after pinging fifo...")
            if buf is not None:
                lines = buf.strip().decode().split('\n')
                for line in lines:
                    line = line.strip()
                    if len(line) == 0 or not '|' in line:
                        continue
                    propid, filepath = line.split('|')
                    self.logger.debug("propid: {}, path: '{}'".format(propid, filepath))
                    if propid != self.propid:
                        self.logger.debug("propid ({}) of file ({}) does not match self ({})".format(propid, filepath, self.propid))
                        continue

                    self.load_file(filepath)

            time.sleep(self.fifo_sleep)

    def load_file(self, filepath):
        self.logger.info("loading file {}".format(filepath))

        frame = Frame(path=filepath)

        if frame.inscode in ('HSC', 'SUP'):
            # Don't display raw HSC frames; mosaic plugin will display them
            return

        frameid = str(frame)
        chname = self.insconfig.getNameByFrameId(frameid)

        image = loader.load_file(filepath, logger=self.logger)
        image.set(name=frameid)

        self.fv.gui_do(self.fv.bulk_add_image, frameid, image, chname)

    #############################################################
    #    Called from Gen2 to deliver a command
    #############################################################

    def callGlobalPlugin2(self, tag, pluginName, methodName, args, kwdargs):

        self.logger.debug("Command received: plugin=%s method=%s args=%s kwdargs=%s tag=%s" % (
                pluginName, methodName, str(args), str(kwdargs), tag))

        # Get object associated with plugin
        if pluginName != 'ANA':
            raise AnaError("plugin name must be ANA")
        obj = self

        # Get method we should call
        if not hasattr(obj, methodName):
            raise Gen2Error("No such method '%s' in plugin object %s" % (
                methodName, pluginName))
        method = getattr(obj, methodName)

        # Make a future that will be resolved by the GUI thread
        p = Bunch.Bunch()
        future = Future.Future(data=p)
        #future.freeze(method, *args, **kwdargs)
        newargs = [tag, future]
        newargs.extend(list(args))
        future.add_callback('resolved',
                            lambda f: self.fv.nongui_do(self.result_cb2,
                                                        future, tag, p))

        future = Future.Future(data=p)
        future.freeze(method, *newargs, **kwdargs)
        future.add_callback('resolved',
                            lambda f: self.fv.nongui_do(self.result_cb1,
                                                        future, tag, p))

        self.fv.gui_do_future(future)
        return ro.OK

    def result_cb1(self, future, tag, data):
        res = future.get_value(suppress_exception=True)
        if isinstance(res, Exception):
            errmsg = str(res)
            resdata = { 'gui_done': time.time(), 'result': 'error',
                        'errmsg': errmsg }

            self._rpc_cleanse(resdata)

            self.logger.error("Command (%s) terminated by exception: %s" % (
                tag, errmsg))
            self.monitor.setvals(['g2task'], tag, **resdata)
        else:
            self.logger.debug("Command made it to the GUI interaction: %s" % (
                tag))

    def result_cb2(self, future, tag, data):
        self.logger.debug("Command termination: %s" % (tag))
        res = future.get_value(suppress_exception=True)

        if isinstance(res, Exception):
            errmsg = str(res)
            data.update({ 'errmsg': errmsg, 'result': 'error' })
            self.logger.error("Command (%s) terminated by exception: %s" % (
                tag, errmsg))
        else:
            self.logger.debug("Command completed GUI interaction: %s" % (
                tag))

        resdata = { 'gui_done': time.time() }
        resdata.update(data)

        self._rpc_cleanse(resdata)
        self.logger.debug("Result is: %s" % (str(resdata)))

        self.monitor.setvals(['g2task'], tag, **resdata)


    def _rpc_cleanse(self, d):
        # RPC cleansing of return data dictionaries
        for key, val in list(d.items()):
            if isinstance(val, np.integer):
                d[key] = int(val)
            elif isinstance(val, np.floating):
                d[key] = float(val)

    #############################################################
    #    Here come the ANA commands
    #############################################################

    def confirmation(self, tag, future,
                     instrument_name=None, title=None, dialog=None):

        # Make sure the specified channel is available
        chname = instrument_name
        if not self.fv.has_channel(chname):
            self.fv.add_channel(chname)

        chinfo = self.fv.get_channelInfo(chname)

        # Deactivate plugin if one is already running
        pluginName = 'Ana_Confirmation'
        if chinfo.opmon.is_active(pluginName):
            chinfo.opmon.deactivate(pluginName)
            self.fv.update_pending()

        p = future.get_data()
        p.setvals(instrument_name=instrument_name, title=title,
                  dialog=dialog)

        # Invoke the operation manually
        chinfo.opmon.start_plugin_future(chname, pluginName, future)


    def userinput(self, tag, future,
                  instrument_name=None, title=None, itemlist=None,
                  iconfile=None, soundfile=None):
        # Make sure the specified channel is available
        chname = instrument_name
        if not self.fv.has_channel(chname):
            self.fv.add_channel(chname)

        chinfo = self.fv.get_channelInfo(chname)

        # Deactivate plugin if one is already running
        pluginName = 'Ana_UserInput'
        if chinfo.opmon.is_active(pluginName):
            chinfo.opmon.deactivate(pluginName)
            self.fv.update_pending()

        p = future.get_data()
        p.setvals(instrument_name=instrument_name, title=title,
                  itemlist=itemlist, iconfile=iconfile, soundfile=soundfile)

        # Invoke the operation manually
        chinfo.opmon.start_plugin_future(chname, pluginName, future)


    def sleep(self, tag, future, sleep_time=None):
        def _sleep(future):
            p = future.get_data()
            p.result = 'ok'
            future.resolve(0)

        # TODO: Don't block the GUI thread!
        #gobject.timeout_add(msecs, _sleep, future)
        time.sleep(sleep_time)

        _sleep(future)


    def __str__(self):
        return 'ana'

#END

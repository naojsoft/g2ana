#
# T. Inagaki
# E. Jeschke
#

import sys
import os
import re
import signal
import shlex
import subprocess
import getpass

from ginga import toolkit
toolkit.use('qt5')
from ginga.gw import Widgets
from ginga.util import paths

from g2base import ssdlog, Bunch
from g2base.remoteObjects import remoteObjects as ro

from g2ana.icons import __file__
icondir, _nm = os.path.split(__file__)


class ANAError(Exception):
    """Base class for exceptions in this module."""
    pass

class Process(object):

    def __init__(self, logger):

        self.logger = logger
        self.processes = []

    def execute(self, args):

        self.logger.debug('executing %s' %args)
        try:

            process = subprocess.Popen(args)
        except Exception as e:
            res = '%s' %str(e)
            self.logger.error('error: execution. %s' %res)
        else:
            if process.pid:
                self.processes.append(process)
            res = 0
        finally:
            return res

    def terminate(self):

        for process in self.processes:
            try:
                self.logger.debug('terminating pid=%d' %process.pid)
                process.terminate()
            except Exception as e:
                self.logger.error('error: terminating process. %s' %e)



class AnaMenu(object):

    def __init__(self, root, logger, rohost, hostname):

        # holds widgets of interest
        self.w = Bunch.Bunch()
        self.w.root = root

        self.logger = logger
        self.process = Process(logger)
        self.hostname = hostname
        self.rohost = rohost
        self.propid = None
        self.propfile = None

        self.__init_propid_entry()

        self.svcname = get_svcname(self.hostname, self.propid, self.logger)

        #self.__set_propfile()
        #self.title_suffix = "\u3041\u306A \u3081\u306C"  # あな めぬ
        title_suffix = "あなめにゅー"
        self.title_suffix = title_suffix.encode(encoding="utf-8").decode()

        self.action_list = [
            ('FOCAS', self.launch_focas),
            ('IRCS', self.launch_ircs),
            ('HDS', self.launch_hds),
            ('MOIRCS', self.launch_moircs),
            ]

    def setup_ui(self):

        self.logger.debug("setting up ana menu gui")
        vbox = Widgets.VBox()

        menubar = Widgets.Menubar()
        menu = menubar.add_name('File')
        menu.add_separator()
        item = menu.add_name('Quit')
        item.add_callback('activated', lambda w: self.quit())
        vbox.add_widget(menubar, stretch=0)

        hbox = Widgets.HBox()
        hbox.set_spacing(2)
        icn = Widgets.Image()
        icn.load_file(os.path.join(icondir, 'sumo.png'))
        hbox.add_widget(icn, stretch=0)

        lbl = Widgets.Label("ANA " + self.title_suffix)
        lbl.set_font('sans', 24)
        hbox.add_widget(lbl, stretch=1)
        vbox.add_widget(hbox, stretch=0)
        self.w.title = lbl

        tb0 = Widgets.Toolbar(orientation='horizontal')
        fr = Widgets.Frame('PropID:')
        fr.set_widget(tb0)
        entry = Widgets.TextEntry()
        self.w.propid = entry
        if self.propid is not None:
            entry.set_text(self.propid)
        tb0.add_widget(entry)
        a = tb0.add_action('Set')
        a.add_callback('activated', self.set_propid_cb)
        vbox.add_widget(fr)

        # buttons for Gen2 application
        tb1 = Widgets.Toolbar(orientation='horizontal')
        fr = Widgets.Frame('Viewers:')
        fr.set_widget(tb1)
        vbox.add_widget(fr)

        tb2 = Widgets.Toolbar(orientation='horizontal')
        fr = Widgets.Frame('Instrument:')
        fr.set_widget(tb2)
        vbox.add_widget(fr)

        tb3 = Widgets.Toolbar(orientation='horizontal')
        fr = Widgets.Frame('Etc:')
        fr.set_widget(tb3)
        vbox.add_widget(fr)

        status = Widgets.StatusBar()
        vbox.add_widget(status)
        self.w.msgbar = status

        # Add some buttons to the tool bars.
        a = tb1.add_action('anaview', toggle=False,
                           iconpath=os.path.join(icondir, 'ginga.svg'),
                           iconsize=(24, 24))
        a.add_callback('activated', lambda w: self.launch_fits_viewer())
        a.set_tooltip("Start anaview FITS viewer")
        a = tb1.add_action('Ds9', toggle=False,
                           iconpath=os.path.join(icondir, 'view-file.png'),
                           iconsize=(24, 24))
        a.add_callback('activated', lambda w: self.launch_ds9())
        a.set_tooltip("Start ds9 FITS viewer")

        for name, action in self.action_list:
            a = tb2.add_action(name, toggle=False,
                               iconpath=os.path.join(icondir, 'camera.png'),
                               iconsize=(24, 24))
            a.add_callback('activated', action)
            a.set_tooltip("Start data analysis package for %s" % (name))

        a = tb3.add_action('Terminal', toggle=False,
                           iconpath=os.path.join(icondir, 'terminal.png'),
                           iconsize=(24, 24))
        a.add_callback('activated', lambda w: self.launch_terminal())
        a.set_tooltip("Start a terminal on analysis server")
        a = tb3.add_action('StatMon', toggle=False,
                           iconpath=os.path.join(icondir, 'statmon.png'),
                           iconsize=(28, 24))
        a.add_callback('activated', lambda w: self.launch_statmon())
        a.set_tooltip("Start Gen2 Status Monitor")
        a = tb3.add_action('SPOT', toggle=False,
                           iconpath=os.path.join(icondir, 'spot.svg'),
                           iconsize=(24, 24))
        a.add_callback('activated', lambda w: self.launch_spot())
        a.set_tooltip("Start Site Planning and Observation Tool")

        self.w.root.set_widget(vbox)
        self.w.root.add_callback('close', lambda w: self.quit())

        self.__init_propid_entry()
        #self.__set_propfile()
        self.logger.debug("ana menu gui done")

    def __set_propfile(self):

        filename = '.ana_propid'
        self.propfile = os.path.join(paths.home, filename)
        self.logger.debug('propfile={}'.format(self.propfile))


    def expand_log(self, expander):

        if expander.get_expanded():
            expander.remove(expander.child)
            self.window.resize(self.window_width, self.window_height)
        else:
            expander.add(self.sw_expander)
            self.c+=1

    def __init_propid_entry(self):
        self.get_propid()

        if self.propid is not None and self.w.has_key('propid'):
            self.w.propid.set_text(self.propid)

    def get_propid(self):
        oid = getpass.getuser()
        self.logger.debug('user={}'.format(oid))
        # for now, handle both u and o account. note: eventually, o-account only
        m = re.search(r'(?<=u|o)\d{5}', oid)
        if m:
            propid = 'o%s' % m.group(0)
            self.set_propid(propid)

    def quit(self):
        self.logger.debug('quitting.')
        # self.remove_propid() # multiple users launch/quit anamenu w/o opening fitsviewer
        self.process.terminate()

        root, self.w.root = self.w.root, None
        root.delete()

    def is_propid(self, propid):
        try:
            m = re.search(r'(?<=o)\d{5}', propid)
        except Exception:
            m = None
        return m

    def set_propid_cb(self, w):
        propid = self.w.propid.get_text().strip()
        if not self.is_propid(propid):
            self.w.msgbar.set_message("Bad propid: '%s'" % (propid))
            w.set_text(self.propid)
            return

        self.set_propid(propid)
        self.__set_propfile()
        self.write_propid()

    def set_propid(self, propid):
        if not self.is_propid(propid):
            raise ValueError("PROP-ID ({}) does not have expected format (oNNMMM)".format(propid))

        self.propid = propid

        port_sfx = int(self.propid[-3:]) * 5
        ds9_port = 22000 + port_sfx
        os.environ['IMTDEV'] = "inet:%d" % (ds9_port)
        os.environ['IMTDEV2'] = "inet:%d" % (ds9_port + 1)
        os.environ['DS9PORT'] = '%d' % (ds9_port)
        self.logger.debug('propid<%s>' % self.propid)

    def __execute(self, cmd, procname):
        ''' execute applications '''
        error = self.process.execute(cmd)

    def remove_propid(self):
        try:
            os.remove(self.propfile)
        except Exception as e:
            self.logger.error('error: removing propfile. %s' %str(e))

    def write_propid(self):
        try:
            with open(self.propfile, 'w') as f:
                f.write(self.propid)
            #os.chmod(self.propfile, 0o666)
        except Exception as e:
            self.logger.error('error: writing propid. %s' %str(e))

    def get_gen2home(self):
        return os.environ['GEN2HOME']

    @property
    def loghome(self):
        logdir = os.path.join(paths.home, '.ana_logs')
        return logdir

    def launch_fits_viewer(self):
        ''' fits viewer '''
        # check GEN2HOST env var is set
        gen2host = os.environ.get('GEN2HOST', '').strip()
        if len(gen2host) == 0:
            os.environ['GEN2HOST'] = self.rohost
        command_line = "anaview -t qt5 --nosplash --numthreads=30 --loglevel=20 --log={0}/anaview_{1}.log".format(self.loghome, self.hostname)

        self.logger.info(f'anaview cmd: {command_line}')
        args = shlex.split(command_line)
        self.__execute(cmd=args, procname='fits viewer')

    def launch_statmon(self):
        ''' statmon '''
        self.logger.info('starting statmon...')
        monport = 34000 + int(self.propid[-3:])
        command_line = f"statmon --numthreads=50 --monport={monport} --loglevel=20 --log={self.loghome}/statmon_{self.hostname}.log"
        self.logger.info(f'statmon cmd: {command_line}')
        args = shlex.split(command_line)
        self.__execute(cmd=args, procname='statmon')

    def launch_spot(self):
        ''' SPOT '''
        self.logger.info('starting SPOT...')
        # Do we need to set CONFHOME here?
        command_line = f"spot --loglevel=20 --log={self.loghome}/spot_{self.hostname}.log"
        self.logger.info(f'spot cmd: {command_line}')
        args = shlex.split(command_line)
        self.__execute(cmd=args, procname='spot')

    def launch_ds9(self):
        ''' ds9 '''
        ds9port = os.environ['DS9PORT']
        command_line = "/usr/local/bin/ds9 -port {}".format(ds9port)
        args = shlex.split(command_line)

        self.logger.debug('ds9_port={}'.format(ds9port))

        self.__execute(cmd=args, procname='ds9')

    def launch_terminal(self):
        ''' gnome-terminal '''
        command_line = "dbus-launch gnome-terminal"
        #command_line = "dbus-launch konsole"
        args = shlex.split(command_line)
        self.__execute(cmd=args, procname='gnome-terminal')

    @property
    def workdir(self):
        return os.path.join('/work', self.propid)

    @property
    def datadir(self):
        return os.path.join('/data', self.propid)

    def __execute_obcp(self, obcp, cmd, insname=None):
        ''' execute obcp '''

        if not self.is_propid(self.propid):
            self.logger.error('error: propid=%s' %str(self.propid))
            return

        command_line = cmd  %(self.propid, obcp, self.datadir, self.workdir)
        args = shlex.split(command_line)

        self.logger.debug('%s cmd=%s' %(insname, args))

        error = self.process.execute(args)
        if not error:
            pass
        else:
            self.logger.error('error: launching %s.. %s'  %(insname, error))

    def launch_hds(self, w):
        self.logger.debug('starting hds....')
        obcp = 'OBCP06'
        cmd = "/home/hds01/hds.ana %s %s %s %s"
        insname = 'HDS'
        self.__execute_obcp(obcp, cmd, insname)

    def launch_ircs(self, w):
        self.logger.debug('starting ircs....')

        obcp = 'OBCP01'
        cmd = "/home/ircs01/ircs/ircs.ana %s %s %s %s"
        insname = 'IRCS'
        self.__execute_obcp(obcp, cmd, insname)

    def launch_focas(self, w):
        self.logger.debug('starting focas....')

        obcp = 'OBCP05'
        cmd = "/home/focas01/focas89.ana %s %s %s %s"
        insname = 'FOCAS'
        self.__execute_obcp(obcp, cmd, insname)

    def launch_moircs(self, w):
        self.logger.debug('starting moircs....')
        obcp = 'OBCP17'
        cmd = "/home/moircs01/moircs/moircs.ana %s %s %s %s"
        insname = 'MOIRCS'
        self.__execute_obcp(obcp, cmd, insname)

    def set_pos(self, x, y):
        self.w.root.move(x, y)

    def set_size(self, wd, ht):
        self.w.root.resize(wd, ht)

    def set_geometry(self, geometry):
        # translation of X window geometry specification WxH+X+Y
        coords = geometry.replace('+', ' +')
        coords = coords.replace('-', ' -')
        coords = coords.split()
        if 'x' in coords[0]:
            # spec includes dimensions
            dim = coords[0]
            coords = coords[1:]
        else:
            # spec is position only
            dim = None

        if dim is not None:
            # user specified dimensions
            dim = [int(x) for x in dim.split('x')]
            self.set_size(*dim)

        if len(coords) > 0:
            # user specified position
            coords = [int(x) for x in coords]
            self.set_pos(*coords)


def get_svcname(hostname, propid, logger):

    hostname = hostname.split('.')[0]
    svcname = "ANA-{}-{}".format(propid, hostname)
    logger.debug('svcname={}'.format(svcname))
    return svcname

def main(options, args):

    hostname = args[0]

    logdir = os.path.join(paths.home, '.ana_logs')
    if not os.path.isdir(logdir):
        os.mkdir(logdir)
    if not options.logstderr:
        options.logfile = os.path.join(logdir,
                                       'anamenu_{}.log'.format(hostname))
    logger = ssdlog.make_logger(hostname, options)

    rohost = options.rohost
    if rohost is None:
        rohost = 'localhost'
    logger.info(f"will connect using remote host '{rohost}'")

    app = Widgets.Application(logger=logger)
    root = app.make_window(title='ANA Menu')

    try:
        ana = AnaMenu(root, logger, rohost, hostname)
        ana.setup_ui()
        root.show()
        ana.set_geometry(options.geometry)

        app.mainloop()

    except KeyboardInterrupt as e:
        print('interrupted by keyboard....')
        logger.debug('Keyboard Interrupt...')
        ana.quit('quit')
        app.quit()

    except Exception as e:
        logger.error('error: starting anamenu. %s' % e)
        #sys.exit(1)
        raise

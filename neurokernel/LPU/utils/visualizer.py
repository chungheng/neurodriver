#!/usr/bin/env python

"""
LPU output visualization.
"""

import collections
from collections import OrderedDict
import itertools
import os

import matplotlib
from matplotlib import cm
from matplotlib.colors import Normalize
import matplotlib.pyplot as plt
plt.ioff() # interactive mode can interfere with frame updates
from matplotlib.animation import FFMpegFileWriter, AVConvFileWriter
from matplotlib.colors import hsv_to_rgb
import networkx as nx
import numpy as np
from scipy.interpolate import griddata
from shutilwhich import which

import simpleio as sio

class visualizer(object):
    """
    Visualize the output produced by LPU models.

    Examples
    --------
    >>> import neurokernel.LPU.utils.visualizer as vis
    >>> V = vis.visualizer()
    >>> config1 = {}
    >>> config1['type'] = 'image'
    >>> config1['shape'] = [32,24]
    >>> config1['clim'] = [-0.6,0.5]
    >>> config2 = config1.copy()
    >>> config2['clim'] = [-0.55,-0.45]
    >>> V.add_LPU('lamina_output.h5', 'lamina.gexf.gz','lamina')
    >>> V.add_plot(config1, 'lamina', 'R1')
    >>> V.add_plot(config2, 'lamina', 'L1')
    >>> V.update_interval = 50
    >>> V.out_filename = 'test.avi'
    >>> V.run()
    """

    def __init__(self):
        self._xlim = [0,1]
        self._ylim = [-1,1]
        self._imlim = [-1, 1]
        self._update_interval = 50
        self._out_file = None
        self._fps = 5
        self._codec = 'libtheora'
        self._config = OrderedDict()
        self._rows = 0
        self._cols = 0
        self._figsize = (16,9)
        self._fontsize = 18
        self._t = 1
        self._dt = 1
        self._data = {}
        self._graph = {}
        self._id_to_data_idx = {}
        self._maxt = None
        self._title = None
        self._FFMpeg = None

    def add_LPU(self, data_file, gexf_file=None, LPU=None, win=None,
                is_input=False, graph=None):
        """
        Add data associated with a specific LPU to a visualization.
        To add a plot containing neurons from a particular LPU,
        the LPU needs to be added to the visualization using this
        function. Note that outputs from multiple neurons can
        be visualized using the same visualizer object.

        Parameters
        ----------
        data_file : str
             Location of the h5 file generated by neurokernel
             containing the output of the LPU
        gexf_file : str
            Location of the gexf file describing the LPU.
            If not specified, it will be assumed that the h5 file
            contains input.
        LPU : str
            Name of the LPU. Will be used as identifier to add plots.
            For input signals, the name of the LPU will be prepended
            with 'input_'. For example::

                V.add_LPU('vision_in.h5', LPU='vision')

            will create the LPU identifier 'input_vision'.
            Therefore, adding a plot depicting this input can be done by::

                V.add_plot({''type':'image',imlim':[-0.5,0.5]},LPU='input_vision)
        win : slice/list
            Can be used to limit the visualization to a specific time window.
        graph : networkx.MultiDiGraph
            Graph describing LPU. If neither `graph` nor `gexf_file`
            are specified, the h5 file will be assumed to contain input.
            Only one of `graph` or `gexf_file` may be set.
        """

        if (gexf_file or graph) and not is_input:
            if gexf_file and not graph:
                self._graph[LPU] = nx.read_gexf(gexf_file)
            elif graph and not gexf_file:
                self._graph[LPU] = graph
            elif graph and gexf_file:
                raise ValueError('gexf_file and graph cannot be set simultaneously')

            # Map neuron ids to index into output data array:
            self._id_to_data_idx[LPU] = {m:i for i, m in \
                enumerate(sorted([int(n) for n, k in \
                                  self._graph[LPU].nodes_iter(True) if k['spiking']]))}
        else:
            if LPU:
                LPU = 'input_' + str(LPU)
            else:
                LPU = 'input_' + str(len(self._data))
            if gexf_file and not graph:
                self._graph[LPU] = nx.read_gexf(gexf_file)
            elif graph and not gexf_file:
                self._graph[LPU] = graph
            elif graph and gexf_file:
                raise ValueError('gexf_file and graph cannot be set simultaneously')
                        
        if not LPU:
            LPU = len(self._data)
        self._data[LPU] = np.transpose(sio.read_array(data_file))
        if win is not None:
            self._data[LPU] = self._data[LPU][:,win]
        if self._maxt:
            self._maxt = min(self._maxt, self._data[LPU].shape[1])
        else:
            self._maxt = self._data[LPU].shape[1]

    def run(self, final_frame_name=None, dpi=300):
        """
        Starts the visualization process.

        If the property `out_filename` is set, the visualization is saved as a
        video to the disk; if not, the animation is displayed on screen.  
        Please refer to documentation of `add_LPU`, `add_plot`
        and the properties of this class on how to configure the visualizer
        before calling this method. An example can be found in the class doc
        string.

        Parameters
        ----------
        final_frame_name : str, optional
            If specified, the final frame of the animation is saved
            to disk.
        dpi : int, default=300
            Resolution at which final frame is saved to disk if
            `final_frame_name` is specified.

        Notes
        -----
        If `update_interval` is set to 0 or None, it will be replaced by the
        index of the final time step. As a result, the visualizer will only
        generate and save the final frame if `final_frame_name` is set.
        """

        self.final_frame_name = final_frame_name
        self._initialize()
        if not self._update_interval:
            self._update_interval = self._maxt - 1
        self._t = self._update_interval + 1
        for _ in range(self._update_interval, 
                       self._maxt, self._update_interval):
            self._update()
        if final_frame_name is not None:
            self.f.savefig(final_frame_name, dpi=dpi)
        if self.out_filename:
            self._close()

    def _set_wrapper(self, obj, name, value):
        name = name.lower()
        func = getattr(obj, 'set_'+name, None)
        if func:
            try:
                func(value, fontsize=self._fontsize, weight='bold')
            except:
                try:
                    func(value)
                except:
                    pass

    def _initialize(self):

        # Count number of plots to create:
        num_plots = 0
        for config in self._config.itervalues():
            num_plots += len(config)

        # Set default grid of plot positions:
        if not self._rows*self._cols == num_plots:
            self._cols = int(np.ceil(np.sqrt(num_plots)))
            self._rows = int(np.ceil(num_plots/float(self._cols)))
        self.f, self.axarr = plt.subplots(self._rows, self._cols,
                                          figsize=self._figsize)

        # Remove unused subplots:
        for i in xrange(num_plots, self._rows*self._cols):
            plt.delaxes(self.axarr[np.unravel_index(i, (self._rows, self._cols))])
        cnt = 0
        self.handles = []
        self.types = []
        keywds = ['handle', 'ydata', 'fmt', 'type', 'ids', 'shape', 'norm']
        # TODO: Irregular grid in U will make the plot better
        U, V = np.mgrid[0:np.pi/2:complex(0, 60),
                        0:2*np.pi:complex(0, 60)]
        X = np.cos(V)*np.sin(U)
        Y = np.sin(V)*np.sin(U)
        Z = np.cos(U)
        self._dome_pos_flat = (X.flatten(), Y.flatten(), Z.flatten())
        self._dome_pos = (X, Y, Z)
        self._dome_arr_shape = X.shape
        if not isinstance(self.axarr, np.ndarray):
            self.axarr = np.asarray([self.axarr])
        for LPU, configs in self._config.iteritems():
            for plt_id, config in enumerate(configs):
                ind = np.unravel_index(cnt, self.axarr.shape)
                cnt+=1

                # Some plot types require specific numbers of
                # neuron ID arrays:
                if 'type' in config:
                    if config['type'] == 'quiver':
                        assert len(config['ids'])==2
                        config['type'] = 0
                    elif config['type'] == 'hsv':
                        assert len(config['ids'])==2
                        config['type'] = 1
                    elif config['type'] == 'image':
                        assert len(config['ids'])==1
                        config['type'] = 2
                    elif config['type'] == 'waveform':
                        config['type'] = 3
                    elif config['type'] == 'raster':
                        config['type'] = 4
                    elif config['type'] == 'rate':
                        config['type'] = 5
                    elif config['type'] == 'dome':
                        config['type'] = 6
                    else:
                        raise ValueError('Plot type not supported')
                else:
                    if str(LPU).startswith('input') and not self._graph[LPU].node[str(config['ids'][0][0])]['spiking']:
                        config['type'] = 2
                    else:
                        config['type'] = 4

                if config['type'] < 3:
                    if not 'shape' in config:

                        # XXX This can cause problems when the number
                        # of neurons is not equal to
                        # np.prod(config['shape'])
                        num_neurons = len(config['ids'][0])
                        config['shape'] = [int(np.ceil(np.sqrt(num_neurons)))]
                        config['shape'].append(int(np.ceil(num_neurons/float(config['shape'][0]))))

                if config['type'] == 0:
                    config['handle'] = self.axarr[ind].quiver(\
                               np.reshape(self._data[LPU][config['ids'][0],0],config['shape']),\
                               np.reshape(self._data[LPU][config['ids'][1],0],config['shape']))
                elif config['type'] == 1:
                    X = np.reshape(self._data[LPU][config['ids'][0],0],config['shape'])
                    Y = np.reshape(self._data[LPU][config['ids'][1],0],config['shape'])
                    V = (X**2 + Y**2)**0.5
                    H = (np.arctan2(X,Y)+np.pi)/(2*np.pi)
                    S = np.ones_like(V)
                    HSV = np.dstack((H,S,V))
                    RGB = hsv_to_rgb(HSV)
                    config['handle'] = self.axarr[ind].imshow(RGB)
                elif config['type'] == 2:
                    if 'trans' in config:
                        if config['trans'] is True:
                            to_transpose = True
                        else:
                            to_transpose = False
                    else:
                        to_transpose = False
                        config['trans'] = False

                    if to_transpose:
                        temp = self.axarr[ind].imshow(np.transpose(np.reshape(\
                                self._data[LPU][config['ids'][0],0], config['shape'])))
                    else:
                        temp = self.axarr[ind].imshow(np.reshape(\
                                self._data[LPU][config['ids'][0],0], config['shape']))



                    temp.set_clim(self._imlim)
                    temp.set_cmap(plt.cm.gist_gray)
                    config['handle'] = temp
                elif config['type'] == 3:
                    fmt = config['fmt'] if 'fmt' in config else '' 
                    self.axarr[ind].set_xlim(self._xlim)
                    self.axarr[ind].set_ylim(self._ylim)
                    if len(config['ids'][0])==1:
                        config['handle'] = self.axarr[ind].plot([0], \
                                            [self._data[LPU][config['ids'][0][0],0]], fmt)[0]
                        config['ydata'] = [self._data[LPU][config['ids'][0][0],0]]
                    else:
                        config['handle'] = self.axarr[ind].plot(self._data[LPU][config['ids'][0],0])[0]

                elif config['type'] == 4:
                    config['handle'] = self.axarr[ind]
                    config['handle'].vlines(0, 0, 0.01)
                    config['handle'].set_ylim([.5, len(config['ids'][0]) + .5])
                    config['handle'].set_ylabel('Neurons',
                                                fontsize=self._fontsize-1, weight='bold')
                    config['handle'].set_xlabel('Time (s)',fontsize=self._fontsize-1, weight='bold')
                    min_id = min(self._id_to_data_idx[LPU].keys())
                    min_idx = self._id_to_data_idx[LPU][min_id]
                    config['handle'].set_xlim([0,len(self._data[LPU][min_idx,:])*self._dt])
                    config['handle'].axes.set_yticks([])
                    config['handle'].axes.set_xticks([])
                elif config['type'] == 6:
                    self.axarr[ind].axes.set_yticks([])
                    self.axarr[ind].axes.set_xticks([])
                    self.axarr[ind] = self.f.add_subplot(self._rows,
                                                         self._cols,
                                                         cnt,
                                                         projection='3d')
                    config['handle' ] = self.axarr[ind]
                    config['handle'].axes.set_yticks([])
                    config['handle'].axes.set_xticks([])
                    config['handle'].xaxis.set_ticks([])
                    config['handle'].yaxis.set_ticks([])
                    config['handle'].zaxis.set_ticks([])
                    if 'norm' not in config.keys():
                        config['norm'] = Normalize(vmin=-70, vmax=0, clip=True)
                    elif config['norm'] == 'auto':
                        if self._data[LPU].shape[1] > 100:
                            config['norm'] = Normalize(vmin = np.min(self._data[LPU][config['ids'][0],100:]),
                                                       vmax = np.max(self._data[LPU][config['ids'][0],100:]),
                                                       clip = True)
                        else:
                            config['norm'] = Normalize(vmin = np.min(self._data[LPU][config['ids'][0],:]),
                                                       vmax = np.max(self._data[LPU][config['ids'][0],:]),
                                                       clip = True)
                            
                    node_dict = self._graph[LPU].node
                    if str(LPU).startswith('input'):
                        latpositions = np.asarray([ node_dict[str(nid)]['lat'] \
                                                    for nid in range(len(node_dict)) \
                                                    if node_dict[str(nid)]['extern'] ])
                        longpositions = np.asarray([ node_dict[str(nid)]['long'] \
                                                     for nid in range(len(node_dict)) \
                                                     if node_dict[str(nid)]['extern'] ])
                    else:
                        latpositions = np.asarray([ node_dict[str(nid)]['lat']
                                                    for nid in config['ids'][0] ])
                        longpositions = np.asarray([ node_dict[str(nid)]['long']
                                                     for nid in config['ids'][0] ])
                    xx = np.cos(longpositions) * np.sin(latpositions)
                    yy = np.sin(longpositions) * np.sin(latpositions)
                    zz = np.cos(latpositions)
                    config['positions'] = (xx, yy, zz)
                    colors = griddata(config['positions'], self._data[LPU][config['ids'][0],0],
                                      self._dome_pos_flat, 'nearest').reshape(self._dome_arr_shape)
                    colors = config['norm'](colors).data
                    colors = np.tile(np.reshape(colors,
                                                [self._dome_arr_shape[0],self._dome_arr_shape[1],1])
                                     ,[1,1,4])
                    colors[:,:,3] = 1.0
                    config['handle'].plot_surface(self._dome_pos[0], self._dome_pos[1],
                                                  self._dome_pos[2], rstride=1, cstride=1,
                                                  facecolors=colors, antialiased=False,
                                                  shade=False)
                    
                for key in config.iterkeys():
                    if key not in keywds:
                        try:
                            self._set_wrapper(self.axarr[ind],key, config[key])
                        except:
                            pass
                        try:
                            self._set_wrapper(config['handle'],key, config[key])
                        except:
                            pass
                
                if config['type']<3:
                    config['handle'].axes.set_xticks([])
                    config['handle'].axes.set_yticks([])

            if self.suptitle is not None:
                self.f.suptitle(self._title, fontsize=self._fontsize+1, x=0.5,y=0.03, weight='bold')

        plt.tight_layout()

        if self.out_filename and self.update_interval:
            if self.FFMpeg is None:
                if which(matplotlib.rcParams['animation.ffmpeg_path']):
                    self.writer = FFMpegFileWriter(fps=self.fps, codec=self.codec)
                elif which(matplotlib.rcParams['animation.avconv_path']):
                    self.writer = AVConvFileWriter(fps=self.fps, codec=self.codec)
                else:
                    raise RuntimeError('cannot find ffmpeg or avconv')
            elif self.FFMpeg:
                if which(matplotlib.rcParams['animation.ffmpeg_path']):
                    self.writer = FFMpegFileWriter(fps=self.fps, codec=self.codec)
                else:
                    raise RuntimeError('cannot find ffmpeg')
            else:
                if which(matplotlib.rcParams['animation.avconv_path']):
                    self.writer = AVConvFileWriter(fps=self.fps, codec=self.codec)
                else:
                    raise RuntimeError('cannot find avconv')

            # Use the output file to determine the name of the temporary frame
            # files so that two concurrently run visualizations don't clobber
            # each other's frames:
            self.writer.setup(self.f, self.out_filename, dpi=80,
                              frame_prefix=os.path.splitext(self.out_filename)[0]+'_')
            self.writer.frame_format = 'png'
            self.writer.grab_frame()
        elif not self.final_frame_name:
            self.f.show()

    def _update(self):
        dt = self._dt
        t = self._t
        for key, configs in self._config.iteritems():
            data = self._data[key]
            for config in configs:
                if config['type'] == 3:
                    if len(config['ids'][0])==1:
                        config['ydata'].extend(np.reshape(np.double(\
                                                                    data[config['ids'][0], \
                                                                         max(0,t-self._update_interval):t]),(-1,)))
                        config['handle'].set_xdata(dt*np.arange(0, t))
                        config['handle'].set_ydata(np.asarray(config['ydata']))
                    else:
                        config['handle'].set_ydata(\
                                                   data[config['ids'][0], t])

                elif config['type']==4:

                    for j, id in enumerate(config['ids'][0]):

                        # Convert neuron id to index into array of generated outputs:
                        try:
                            idx = self._id_to_data_idx[key][id]
                        except:
                            continue
                        else:
                            for time in np.where(data[idx, max(0,t-self._update_interval):t])[0]:
                                config['handle'].vlines(float(t-time)*self._dt,j+0.75, j+1.25)
                elif config['type'] == 0:
                    shape = config['shape']
                    ids = config['ids']
                    config['handle'].U = np.reshape(data[ids[0], t],shape)
                    config['handle'].V = np.reshape(data[ids[1], t],shape)
                elif config['type']==1:
                    shape = config['shape']
                    ids = config['ids']
                    X = np.reshape(data[ids[0], t],shape)
                    Y = np.reshape(data[ids[1], t],shape)
                    V = (X**2 + Y**2)**0.5
                    H = (np.arctan2(X,Y)+np.pi)/(2*np.pi)
                    S = np.ones_like(V)
                    HSV = np.dstack((H,S,V))
                    RGB = hsv_to_rgb(HSV)
                    config['handle'].set_data(RGB)
                elif config['type'] == 2:
                    ids = config['ids']
                    if config['trans']:
                        config['handle'].set_data(
                            np.transpose(np.reshape(data[ids[0], t], config['shape'
                                                                        ])))
                    else:
                        config['handle'].set_data(
                            np.reshape(data[ids[0], t], config['shape']))
                elif config['type'] == 6:
                    ids = config['ids']
                    d = data[ids[0], t]
                    colors = griddata(config['positions'], d,
                                      self._dome_pos_flat, 'nearest').reshape(self._dome_arr_shape)
                    colors = config['norm'](colors).data
                    colors = np.tile(np.reshape(colors,
                                                [self._dome_arr_shape[0],self._dome_arr_shape[1],1])
                                     ,[1,1,4])
                    colors[:,:,3] = 1.0

                    config['handle'].clear()
                    config['handle'].xaxis.set_ticks([])
                    config['handle'].yaxis.set_ticks([])
                    config['handle'].zaxis.set_ticks([])
                    
                    config['handle'].plot_surface(self._dome_pos[0], self._dome_pos[1],
                                                  self._dome_pos[2], rstride=1, cstride=1,
                                                  facecolors=colors, antialiased=False,
                                                  shade=False)
                keywds = ['handle', 'ydata', 'fmt', 'type', 'ids', 'shape', 'norm']
                for key in config.iterkeys():
                    if key not in keywds:
                        try:
                            self._set_wrapper(self.axarr[ind],key, config[key])
                        except:
                            pass

                        try:
                            self._set_wrapper(config['handle'],key, config[key])
                        except:
                            pass
        self.f.canvas.draw()
        if self.out_filename:
            self.writer.grab_frame()

        self._t+=self._update_interval

    def add_plot(self, config_dict, LPU, names=[''], shift=0):
        """
        Add a plot to the visualizer

        Parameters
        ----------
        config_dict: dict
            A dictionary specifying the plot attributes. The attribute
            names should be the keys.
            
            The following are the plot attributes that can be specfied using
            this dict.

            type - str
                This specifies the type of the plot. Has to be one of
                ['waveform', 'raster', 'image','hsv','quiver', 'dome']
                For plots of type 'dome', lat and long are required
                to be specified in the gexf file.
            ids - dict with either 1 or 2 entries
                Specifies the neuron ids from the associated LPU.
                The keys should be in [0,1] and the values
                should be a list of ids.
                For example::

                    {'ids':{0:[1,2]}}

                will plot neurons with ids 1 and 2.
                Two entries in the dictionary  are needed if the plot is
                of type 'hsv' or 'quiver'
                For example::

                     {'ids':{0:[:768],1:[768:1536]},'type':'HSV'}

                can be used to generate a HSV plot where the hue channel is
                controlled by the angle of the vector defined by the membrane
                potentials of the neurons with ids [:768] and [768:1536] and
                the value will be the magnitude of the same vector. 
            
                This parameter is optional for the following cases::

                    1) The plot is associated with input signals.
                    2) The names parameter is specified.

                If the above doesn't hold, this attribute needs to be specified.

            shape - list or tuple with two entries
                This attribute specifies the dimensions for plots of type image,
                hsv or quiver.
  
            title - str
                Optional. Can be used to control the title of the plot.

            
            In addition to the above, any parameter supported by matlpotlib
            for the particular type of plot can be specified.
            For example - 'imlim','clim','xlim','ylim' etc.              
        LPU: str
            The name of the LPU associated to this plot.
        names: list
            Optional. A list of str specifying the neurons
            to plot. Can be used instead of specifying ids in the
            config_dict. The gexf file of the LPU needs to have
            the name attribute in order for this to be used.
        """

        config = config_dict.copy()
        if not isinstance(names, list):
            names = [names]
        if not LPU in self._config:
            self._config[LPU] = []
        if 'ids' in config:
            # XXX should check whether the specified ids are within range
            self._config[LPU].append(config)
        elif str(LPU).startswith('input'):
            config['ids'] = [range(0, self._data[LPU].shape[0])]
            self._config[LPU].append(config)
        else:
            config['ids'] = {}
            for i,name in enumerate(names):
                config['ids'][i]=[]
                for id in range(len(self._graph[LPU].node)):
                    if self._graph[LPU].node[str(id)]['name'] == name:
                        config['ids'][i].append(id-shift)
            self._config[LPU].append(config)
        if not 'title' in config:
            if names[0]:
                config['title'] = "{0} - {1}".format(str(LPU),str(names[0]))
            else:
                if str(LPU).startswith('input_'):
                    config['title'] = LPU.split('_',1)[1] + ' - ' + 'Input'
                else:
                    config['title'] = str(LPU)

    def _close(self):
        self.writer.finish()
        plt.close(self.f)

    @property
    def xlim(self):
        """
        X-axis limits for all the raster and waveform plots. Can be superseded
        for individual plots by specifying xlim in the config_dict for that
        plot.

        See Also
        --------
        add_plot

        """
        return self._xlim

    @xlim.setter
    def xlim(self, value):
        self._xlim = value

    @property
    def ylim(self):
        """
        Get or set the limits of the y-axis for all the raster and waveform plots.
        Can be superseded for individual plots by specifying xlim in the config_dict
        for that plot.

        See Also
        --------
        add_plot
        """
        return self._ylim

    @ylim.setter
    def ylim(self, value):
        self._ylim = value

    @property
    def FFMpeg(self): return self._FFMpeg
    
    @FFMpeg.setter
    def FFMpeg(self, value):
        self._FFMpeg = value

    @property
    def imlim(self): return self._imlim

    @imlim.setter
    def imlim(self, value):
        self._imlim = value

    @property
    def out_filename(self): return self._out_file

    @out_filename.setter
    def out_filename(self, value):
        assert(isinstance(value, str))
        self._out_file = value

    @property
    def fps(self): return self._fps

    @fps.setter
    def fps(self, value):
        assert(isinstance(value, int))
        self._fps = value

    @property
    def codec(self): return self._codec

    @codec.setter
    def codec(self, value):
        assert(isinstance(value, str))
        self._codec = value

    @property
    def rows(self): return self._rows

    @rows.setter
    def rows(self, value):
        self._rows = value

    @property
    def cols(self): return self._cols

    @cols.setter
    def cols(self, value):
        self._cols = value

    @property
    def dt(self): return self._dt

    @dt.setter
    def dt(self, value):
        self._dt = value

    @property
    def figsize(self): return self._figsize

    @figsize.setter
    def figsize(self, value):
        assert(isinstance(value, tuple) and len(value)==2)
        self._figsize = value

    @property
    def fontsize(self): return self._fontsize

    @fontsize.setter
    def fontsize(self, value):
        self._fontsize = value

    @property
    def suptitle(self): return self._title

    @suptitle.setter
    def suptitle(self, value):
        self._title = value

    @property
    def update_interval(self):
        """
        Update interval (in number of time steps) for the animation.
        If set to 0 or None, `update_interval` will be set to the index of the
        final step. As a consequence, only the final frame will be generated.
        """
        return self._update_interval

    @update_interval.setter
    def update_interval(self, value):
        self._update_interval = value

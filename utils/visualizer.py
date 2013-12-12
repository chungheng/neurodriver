#!/usr/bin/env python

"""
LPU output visualization.
"""

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.animation import FFMpegWriter, FFMpegFileWriter
from matplotlib.colors import hsv_to_rgb
import networkx as nx
import simpleio as sio

class visualizer(object):
    """
    Visualize the output produced by LPU models.

    Example
    -------
    import neurokernel.LPU.utils.visualizer as vis
    V = vis.visualizer()
    config1 = {}
    config1['type'] = 'image'
    config1['shape'] = [32,24]
    config1['clim'] = [-0.6,0.5]
    config2 = config1.copy()
    config2['clim'] = [-0.55,-0.45]
    V.add_LPU('lamina_output.h5', 'lamina.gexf.gz','lamina')
    V.add_plot(config1, 'lamina', 'R1')
    V.add_plot(config1, 'lamina', 'L1')
    V._update_interval = 50
    V.out_filename = 'test.avi'
    V.run()
    """
    
    def __init__(self):
        self._xlim = [0,1]
        self._ylim = [-1,1]
        self._imlim = [-1, 1]
        self._update_interval = 50
        self._out_file = None
        self._fps = 5
        self._codec = 'h264'
        self._config = {};
        self._rows = 0
        self._cols = 0
        self._figsize = (16,9)
        self._fontsize = 18
        self._t = 1
        self._dt = 1
        self._data = {}
        self._graph = {}
        self._maxt = None
        self._title = None

    def add_LPU(self, data_file, gexf_file=None, LPU=None, win=None):
        '''
        Add data associated with a specific LPU to a visualization.

        To add a plot containing neurons from a particular LPU,
        the LPU needs to be added to the visualization using this
        function. Not that outputs from multiple neurons can
        be visualized using the same visualizer object.

        Parameters
        ----------
        data_file: str
             Location of the h5 file generated by neurokernel
             containing the output of the LPU

        gexf_file: str
            Location of the gexf file describing the LPU.
            If not specified, it will be assumed that the h5 file
            contains input.

        LPU: str
            Name of the LPU. Will be used as identifier to add plots.
       
        '''
        if gexf_file:
            self._graph[LPU] = nx.read_gexf(gexf_file)
        else:
            if LPU:
                LPU = 'input_' + str(LPU)
            else:
                LPU = 'input_' + str(len(self._data))
        if not LPU:
            LPU = len(self._data)
        self._data[LPU] = np.transpose(sio.read_array(data_file))
        if win is not None:
            self._data[LPU] = self._data[LPU][:,win]
        if self._maxt:
            self._maxt = min(self._maxt, self._data[LPU].shape[1])
        else:
            self._maxt = self._data[LPU].shape[1]

    def run(self, final_frame_name=None):
        '''
        Starts the visualization process. If out_filename is specified,
        will create a movie. If not, the visualization will be done in
        a figure window, without it being saved.
        The final frame is saved to the specified file name.
        '''
        
        self._initialize()
        self._t = self._update_interval+1
        for i in range(self._update_interval,self._maxt, self._update_interval):
            self.update()
        if final_frame_name is not None:
            self.f.savefig(final_frame_name, dpi=300)
        if self.out_filename:
            self.close()
            
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
        keywds = ['handle', 'ydata', 'fmt', 'type', 'ids', 'shape'] 
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
                    else:
                        raise ValueError('Plot type not supported')
                else:
                    if str(LPU).startswith('input') or not self._graph[LPU][str(config['ids'][0])]['spiking']:
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
                    temp = self.axarr[ind].imshow(np.reshape(\
                                self._data[LPU][config['ids'][0],0],config['shape']))
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
                    config['handle'].set_xlabel('Time',fontsize=self._fontsize-1, weight='bold')
                    config['handle'].set_xlim([0,len(self._data[LPU][config['ids'][0][0],:])*self._dt])
                    config['handle'].axes.set_yticks([])
                    config['handle'].axes.set_xticks([])
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

        if self.out_filename:
            self.writer = FFMpegFileWriter(fps=self.fps, codec=self.codec)
            self.writer.setup(self.f, self.out_filename, dpi=80)
            self.writer.frame_format = 'png'
            self.writer.grab_frame()
        else:
            self.f.show()

    def update(self):
        dt = self._dt
        t = self._t
        for key, configs in self._config.iteritems():
            data = self._data[key]
            for config in configs:
                if config['type'] == 3:
                    if len(config['ids'][0])==1:
                        config['ydata'].extend(np.double(\
                                        data[config['ids'][0], \
                                                  max(0,t-self._update_interval):t]))
                        config['handle'].set_xdata(dt*np.arange(0, t))
                        config['handle'].set_ydata(np.asarray(config['ydata']))
                    else:
                        config['handle'].set_ydata(\
                                        data[config['ids'][0], t])

                elif config['type']==4:
                    for j,id in enumerate(config['ids'][0]):
                        for time in np.where(data[id,max(0,t-self._update_interval):t])[0]:
                            config['handle'].vlines(float(t-time)*self._dt,j+0.75, j+1.25)
                else:
                    if config['type'] == 0:
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
                        shape = config['shape']
                        ids = config['ids']
                        config['handle'].set_data(np.reshape(data[ids[0], t],shape))
                    
        self.f.canvas.draw()
        if self.out_filename:
            self.writer.grab_frame()

        self._t+=self._update_interval
            
    def add_plot(self, config_dict, LPU=0, names=[''], shift=0):
        config = config_dict.copy()
        if not isinstance(names, list):
            names = [names]
        if not LPU in self._config:
            self._config[LPU] = []
        if 'ids' in config:
            self._config[LPU].append(config)
        elif str(LPU).startswith('input'):
            config['ids'] = [range(0, self._data['input'].shape[0])]
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

    def close(self):
        self.writer.finish()

    @property
    def xlim(self): return self._xlim

    @xlim.setter
    def xlim(self, value):
        self._xlim = value

    @property
    def ylim(self): return self._ylim

    @ylim.setter
    def ylim(self, value):
        self._ylim = value

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
    def update_interval(self): return self._update_interval

    @update_interval.setter
    def update_interval(self, value):
        self._update_interval = value

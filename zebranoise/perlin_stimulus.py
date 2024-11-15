import hashlib
import os
import warnings
import tempfile
from subprocess import call
from pathlib import Path
import numpy as np
import imageio
from imageio_ffmpeg import get_ffmpeg_exe

from . import _perlin
from .util import generate_frames, filter_frames, filter_frames_index_function, XYSCALEBASE, discretize, apply_filters


class PerlinStimulus:
    """Class to generate a Perlin noise stimulus.

    This is the "heavy duty" way of generating stimuli, mostly for experimenting
    with new Perlin-based stimuli.  If you would just like to generate zebra
    noise, use the "zebra_noise" function instead, which is faster and more
    memory efficient.

    To generate noise, instantiate this method.  This will automatically
    generate Perlin noise which you can save, filter, etc.

    """
    def __init__(self, xsize, ysize, tdur, levels=10, xyscale=.2, tscale=50, fps=30, xscale=1.0, yscale=1.0, seed=0, demean="both", cachedir="perlcache", delay_batch=False):
        """Initialise Perlin noise stimulus.

        Parameters
        ----------
        xsize,ysize : int > 0
            The number of pixels in the x or y dimension
        tdur : int > 0
            The duration of the stimulus, in seconds.  Sometimes will be slightly longer.
        levels : int > 0, default: 10
            The number of spatial scales to include.  The default is usually okay.
        xyscale : float ∈ [0,1], default: 0.5
            The spatial grain scale of the noise, larger is more granular
        xscale : float, default: 1.0
            The spatial scale in x, larger is a bigger scale
        yscale : float, default: 1.0
            The spatial scale in y, larger is a bigger scale
        tscale : int > 0, default: 1
            The temporal scaling of the noise, larger is slower.
        fps : int > 0, default: 30
            Frames per second of the stimulus
        seed : int ∈ [0, 255], default: 0
            Random seed for the noise
        demean : {'both', 'time', 'space', 'none'}, default: 'both'
            Dimensions across which to fix the mean to zero
        cachedir : str
            A file path to the cache directory.  Will contain large files.
        delay_batch : bool
            If true, do not immediately generate perlin noise.  Manually call self.generate_batch() instead.

        Notes
        -----
        This causes data to be written to the disk and long-running
        computations to be performed

        """
        assert demean in ["both", "time", "space", "none"]
        tsize = int(tdur*fps)
        tscale = tscale
        self.ratio = xsize/ysize*XYSCALEBASE
        assert self.ratio == int(self.ratio), f"Ratio between x and y times {XYSCALEBASE} must be an integer"
        self.ratio = int(self.ratio)
        textra = (tscale - (tsize % tscale)) % tscale
        if textra > 0:
            warnings.warn(f"Adding {textra} extra timepoints to make tscale a multiple of tdur")
        tsize += round(textra)
        self.size = (xsize, ysize, tsize)
        assert self.size[0] >= self.size[1], "Wrong orientation"
        self.fps = fps
        self.seed = seed
        self.cachedir = Path(cachedir)
        self.cachedir.mkdir(exist_ok=True)
        self.tmpdir = Path(tempfile.mkdtemp())
        self.xyscale = xyscale
        self.tscale = tscale
        self.levels = levels
        self.demean = demean
        self.xscale = xscale
        self.yscale = yscale
        self.batch_size = int(400000000/(self.size[0]*self.size[1]))
        #self.batch_size = int(400000/(self.size[0]*self.size[1]))
        if self.batch_size % 2 == 1: # Make sure it is an even number
            self.batch_size += 1
        if not delay_batch:
            self.generate_batch()
    def cache_filename(self, batch=None):
        """Return the filename for the cache.

        The cache is split up into different batches, saved in different files

        Parameters
        ----------
        batch : int, 'stats', or None
            The ID of the batch to find.

        Returns
        -------
        str
            The filename of the cache
        """
        h = hashlib.md5(str((self.size, self.fps, self.seed, self.xyscale, self.tscale, self.levels, self.demean)).encode()).hexdigest()
        if batch is None:
            return str(self.cachedir.joinpath(f"perlcache_{h}.npy"))
        if batch == "stats":
            return str(self.cachedir.joinpath(f"perlcache_{h}_stats.npz"))
        return str(self.cachedir.joinpath(f"perlcache_{h}_{batch}.npy"))
    def generate_frame(self, t=0, filters=[]):
        """Generate and return a single image of noise.


        Parameters
        ----------
        t : float
            the frame at which to generate the image
        filters : list of str and/or (str, ...) tuples
            A list of filters to apply to the stimulus.  If a filter requires
            parameters, pass a tuple, where the first element is the name of
            the filter and the subsequent elements are the parameters.

        Returns
        -------
        2-dimensional ndarray
            An image of the noise
        """
        arr = generate_frames(self.size[0], self.size[1], self.size[2], timepoints=[t] if not hasattr(t, "__iter__") else t, levels=self.levels,
                              xyscale=self.xyscale, tscale=self.tscale, xscale=self.xscale,
                              yscale=self.yscale, fps=self.fps, seed=self.seed)
        if self.demean in ["both", "time"]:
            arr -= np.mean(arr, axis=(0,1), keepdims=True)
        arr = apply_filters(arr, filters)
        return arr.squeeze()

    def generate_batch(self):
        """Create the stimulus

        Runs the _perlin C module and saves the output in batches.

        If this function has already been run before and has been cached on the
        filesytem, automatically load the statistics from it.  Otherwise,
        generate the stimuli and cache them.
        """
        # If the cache already exists, load the statistics (used for
        # normalisation) and exit immediately.
        if os.path.isfile(self.cache_filename("stats")):
            stats = np.load(self.cache_filename("stats"))
            self.min_ = stats['min_']
            self.max_ = stats['max_']
            self.nframes = stats['nframes']
            return
        # Generate the stimuli and save the means and mins/maxes.  If we are
        # demeaning across space, we won't end up using the mins or maxes saved
        # here.
        means_t = []
        means_xy = []
        weights = []
        mins = []
        maxes = []
        for k in range(0, int(np.ceil(self.size[2]/self.batch_size))):
            print(f"Generating batch {k}")
            arr = generate_frames(self.size[0], self.size[1], tsize=self.size[2],
                                  timepoints=list(range(k*self.batch_size,min(self.size[2],(k+1)*self.batch_size))),
                                  levels=self.levels, xyscale=self.xyscale, tscale=self.tscale, xscale=self.xscale,
                                  yscale=self.yscale, fps=self.fps, seed=self.seed)
            if self.demean in ["both", "time"]:
                arr -= np.mean(arr, axis=(0,1), keepdims=True)
            mins.append(np.min(arr))
            maxes.append(np.max(arr))
            means_t.append(np.mean(arr, axis=2))
            weights.append(arr.shape[2])
            np.save(self.cache_filename(k), arr.astype("float16"))
            del arr
        # Compute the spatial mean (across t)
        mean_t = np.sum(means_t*(np.asarray(weights)[:,None,None]), axis=0)/np.sum(weights)
        nframes = np.sum(weights)
        # Optionally remove the spatial mean.  If so, iterate through and
        # update all of the saved data files to remove the spatial mean.
        if self.demean in ["both", "space"]:
            k = 0
            mins = []
            maxes = []
            while os.path.isfile(self.cache_filename(k)):
                arr = np.load(self.cache_filename(k)).astype("float32")
                arr -= mean_t[:,:,None]
                mins.append(np.min(arr))
                maxes.append(np.max(arr))
                np.save(self.cache_filename(k), arr.astype("float16"))
                del arr
                k += 1
        min_ = np.min(mins)
        max_ = np.max(maxes)
        # Save the mins and maxes.
        np.savez_compressed(self.cache_filename("stats"), min_=min_, max_=max_, nframes=nframes)
        self.min_ = min_
        self.max_ = max_
        self.nframes = nframes
    def save_grey_pad(self, fn, dur, bitrate=20):
        """Create a grey screen video which can be used to pad"""
        one_frame = np.load(self.cache_filename(0), mmap_mode='r')[:,:,0].astype('uint8') * 0 + 127
        imageio.imsave(self.tmpdir.joinpath("_grey.tif"), one_frame, format="pillow", compression="tiff_adobe_deflate")
        n_frames = int(dur * self.fps)
        for i in range(0, n_frames):
            os.link(self.tmpdir.joinpath("_grey.tif"), self.tmpdir.joinpath(f"_frame{i:05}.tif"))
        if fn[-4:] != ".mp4":
            fn += ".mp4"
        call([get_ffmpeg_exe(), "-r", str(self.fps), "-i", str(self.tmpdir.joinpath("_frame%5d.tif")), "-c:v", "mpeg2video", "-an", "-b:v", f"{bitrate}M", fn])
        for p in self.tmpdir.glob("_frame*.tif"):
            p.unlink()
        self.tmpdir.joinpath("_grey.tif").unlink()
    def save_video(self, fn, loop=1, filters=[], bitrate=20):
        """Save the filtered stimulus.

        Parameters
        ----------
        fn : str
            The file name to save the video
        loop : int > 0
            The number of times the stimulus should loop in the saved video
        filters : list of str and/or (str, ...) tuples
            A list of filters to apply to the stimulus.  If a filter requires
            parameters, pass a tuple, where the first element is the name of
            the filter and the subsequent elements are the parameters.
        bitrate : int > 0
            The bitrate in megabits per second.  The default is good for binary
            videos and pure noise, but a higher value may be necessary if
            using the "wood" filter.
        """
        if Path(fn).exists():
            raise IOError("Output video file already exists!")
        i = 0
        k = 0
        shift = 0
        filtind = filter_frames_index_function(filters, nframes=self.nframes)
        while os.path.isfile(self.cache_filename(k)):
            data = np.load(self.cache_filename(k)).astype("float32")
            # Renormalise using precomputed mins/maxes
            data -= self.min_
            data *= 1/(self.max_-self.min_)
            # Apply filters
            for f in filters:
                if isinstance(f, str):
                    n = f
                    if n=="photodiode_ibl":
                        np.random.seed(1234)
                        seq = np.tile(np.random.random(3600), (8,1)).T.flatten()
                        args = (seq[shift:(shift+data.shape[2])] > .5).astype(np.int8)
                    else:
                        args = []
                else:
                    n = f[0]
                    if n=="photodiode_ibl":
                        print(data.shape[2])
                        args = f[1][shift:(shift+data.shape[2])].astype(np.int8)
                    else:
                        args = f[1:]
                data = filter_frames(data, n,*args)
            data = discretize(data)
            assert data.dtype == 'uint8'
            for j in range(0, data.shape[2]):
                imageio.imsave(self.tmpdir.joinpath(f"_frame{filtind(i):05}.tif"), data[:,:,j], format="pillow", compression="tiff_adobe_deflate")
                i += 1
            k += 1
            shift += data.shape[2]
            del data
        n_frames = i
        for j in range(1, loop):
            for i in range(0, n_frames):
                os.link(self.tmpdir.joinpath(f"_frame{i:05}.tif"), self.tmpdir.joinpath(f"_frame{(i+j*n_frames):05}.tif"))
        if fn[-4:] != ".mp4":
            fn += ".mp4"
        call([get_ffmpeg_exe(), "-r", str(self.fps), "-i", str(self.tmpdir.joinpath("_frame%5d.tif")), "-c:v", "mpeg2video", "-an", "-b:v", f"{bitrate}M", fn])
        for p in self.tmpdir.glob("_frame*.tif"):
            p.unlink()

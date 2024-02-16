from subprocess import call
import imageio
import hashlib
import os
from . import _perlin
import numpy as np
import warnings
import scipy.ndimage
from pathlib import Path
import tempfile

class Perl:
    """Class to generate a Perlin noise stimulus.

    To generate noise, instantiate this method.  This will automatically
    generate Perlin noise which you can save, filter, etc.
    """
    XYSCALEBASE = 100
    def __init__(self, xsize, ysize, tdur, levels=10, xyscale=.5, tscale=1, fps=30, seed=0, demean="both", cachedir="perlcache"):
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
            The spatial scaling of the noise, smaller is broader/wider
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

        Notes
        -----
        This causes data to be written to the disk and long-running
        computations to be performed

        """
        assert demean in ["both", "time", "space", "none"]
        tsize = int(tdur*fps)
        self.ratio = xsize/ysize*self.XYSCALEBASE
        assert self.ratio == int(self.ratio), "Ratio between x and y times 100 must be an integer"
        self.ratio = int(self.ratio)
        textra = (tscale - (tsize % tscale)) % tscale
        if textra > 0:
            warnings.warn(f"Adding {textra} extra timepoints to make tscale a multiple of tdur")
        tsize += textra
        self.size = (xsize, ysize, tsize)
        assert self.size[0] > self.size[1], "Wrong orientation"
        self.fps = fps
        self.seed = seed
        self.cachedir = Path(cachedir)
        self.cachedir.mkdir(exist_ok=True)
        self.tmpdir = Path(tempfile.mkdtemp())
        self.xyscale = xyscale
        self.tscale = tscale
        self.levels = levels
        self.demean = demean
        self.batch_size = int(400000000/(self.size[0]*self.size[1]))
        #self.batch_size = int(400000/(self.size[0]*self.size[1]))
        if self.batch_size % 2 == 1: # Make sure it is an even number
            self.batch_size += 1
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
    @classmethod
    def discretize(cls, im):
        """Convert movie to an unsigned 8-bit integer

        Parameters
        ----------
        im : 3D float ndarray, values ∈ [0,1]
            Pink noise movie

        Returns
        -------
        3D int ndarray, values ∈ [0,255]
            Pink noise movie
        """
        im *= 255
        ret = im.astype(np.uint8)
        return ret
    @classmethod
    def filter(cls, im, filt, *args):
        """Apply a filter to a batch

        Parameters
        ----------
        im : 3D float ndarray, values ∈ [0,1]
            Pink noise movie
        filt : str
            The name of the filter
        *args : tuple
            Extra arguments are passed to the filter

        Returns
        -------
        im : 3D float ndarray, values ∈ [0,1]
            Filtered pink noise movie
        """
        if filt == "threshold":
            return (im>args[0]).astype(np.float32)
        if filt == "softthresh":
            return 1/(1+np.exp(-args[0]*(im-.5)))
        if filt == "comb":
            return (im//args[0] % 2 == 1).astype(np.float32)
        if filt == "invert":
            return 1-im
        if filt == "reverse":
            return im # We need to use filter_index_function for this
        if filt == "blur":
            return np.asarray([scipy.ndimage.filters.gaussian_filter(im.astype(np.float32)[:,:,i], args[0], mode='wrap') for i in range(0, im.shape[2])]).transpose([1,2,0])
        if filt == "wood":
            return (im % args[0]) / args[0]
        if filt == "center":
            return 1-(np.abs(im-.5)*2)
        if filt == "photodiode":
            im = im.copy()
            s = args[0]
            im[:s,-s:,::2] = 0
            im[:s,-s:,1::2] = 1
            return im
        if filt == "photodiode_anywhere":
            im = im.copy()
            x = args[0]
            y = args[1]
            s = args[2]
            im[y:(y+s),x:(x+s),::2] = 0
            im[y:(y+s),x:(x+s),1::2] = 1
            return im
        if filt == "photodiode_b2":
            im = im.copy()
            s = 125
            im[:s,-s:,::2] = 0
            im[:s,-s:,1::2] = 1
            return im
        if filt == "photodiode_fusi":
            im = im.copy()
            s = 75
            im[:s,-s:,::2] = 0
            im[:s,-s:,1::2] = 1
            return im
        if filt == "photodiode_bscope":
            im = im.copy()
            s = 100
            im[-s:,:s,::2] = 0
            im[-s:,:s,1::2] = 1
            return im
        if callable(filt):
            return filt(im)
        raise ValueError("Invalid filter specified")
    def filter_index_function(self, filters):
        """Reordering frames in the video based on the filter.


        Parameters
        ----------
        filters : list of strings or tuples
            the list of filters passed to save_video

        Returns
        -------
        function mapping int -> int
            Reindexing function

        Notes
        -----
        Some filters may need to operate on the global video instead of in
        batches.  However, for large videos, batches are necessary due to
        limited amounts of RAM.  Thus, this function should return another
        function which takes an index as input and outputs a new index,
        remapping the initial pink noise frame to the output video frame.  This
        was primarily designed to support reversing the video, but it might be
        useful for other things too.

        """
        if "reverse" in filters:
            return lambda x : self.nframes - x - 1
        return lambda x : x

    def generate_batch(self):
        """Create the pink noise stimuli

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
        # Use the temporal scale and number of timepoints to compute how many
        # units to make the stimulus across the temporal dimension
        tunits = int(self.size[2]/self.tscale)
        ts_all = np.arange(0, self.size[2], dtype="float32")/self.tscale
        # Generate the stimuli and save the means and mins/maxes.  If we are
        # demeaning across space, we won't end up using the mins or maxes saved
        # here.
        means_t = []
        means_xy = []
        weights = []
        mins = []
        maxes = []
        for k in range(0, int(np.ceil(len(ts_all)/self.batch_size))):
            ts = ts_all[(k*self.batch_size):((k+1)*self.batch_size)]
            print("batch", k, len(ts_all), self.batch_size, len(ts))
            arr = _perlin.make_perlin(np.arange(0, self.size[0], dtype="float32")/self.size[1], # Yes, divide by y size
                                              np.arange(0, self.size[1], dtype="float32")/self.size[1],
                                              ts,
                                              octaves=self.levels,
                                              persistence=self.xyscale,
                                              repeatx=self.ratio,
                                              repeaty=self.XYSCALEBASE,
                                              repeatz=tunits,
                                              base=self.seed)
            arr = arr.swapaxes(0,1)
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
        call(["ffmpeg", "-r", str(self.fps), "-i", str(self.tmpdir.joinpath("_frame%5d.tif")), "-c:v", "mpeg2video", "-an", "-b:v", f"{bitrate}M", fn])
        call([f"rm "+str(self.tmpdir.joinpath("_frame*.tif"))], shell=True)
        call([f"rm "+str(self.tmpdir.joinpath("_grey.tif"))], shell=True)
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
            videos and pure pink noise, but a higher value may be necessary if
            using the "wood" filter.
        """
        if Path(fn).exists():
            raise IOError("Output video file already exists!")
        i = 0
        k = 0
        filtind = self.filter_index_function(filters)
        while os.path.isfile(self.cache_filename(k)):
            data = np.load(self.cache_filename(k)).astype("float32")
            # Renormalise using precomputed mins/maxes
            data -= self.min_
            data *= 1/(self.max_-self.min_)
            # Apply filters
            for f in filters:
                if isinstance(f, str):
                    n = f
                    args = []
                else:
                    n = f[0]
                    args = f[1:]
                data = self.filter(data, n, *args)
            data = self.discretize(data)
            assert data.dtype == 'uint8'
            for j in range(0, data.shape[2]):
                imageio.imsave(self.tmpdir.joinpath(f"_frame{filtind(i):05}.tif"), data[:,:,j], format="pillow", compression="tiff_adobe_deflate")
                i += 1
            k += 1
            del data
        n_frames = i
        for j in range(1, loop):
            for i in range(0, n_frames):
                os.link(self.tmpdir.joinpath(f"_frame{i:05}.tif"), self.tmpdir.joinpath(f"_frame{(i+j*n_frames):05}.tif"))
        if fn[-4:] != ".mp4":
            fn += ".mp4"
        call(["ffmpeg", "-r", str(self.fps), "-i", str(self.tmpdir.joinpath("_frame%5d.tif")), "-c:v", "mpeg2video", "-an", "-b:v", f"{bitrate}M", fn])
        call([f"rm "+str(self.tmpdir.joinpath("_frame*.tif"))], shell=True)

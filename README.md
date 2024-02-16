This library will efficiently generate visual stimulus videos using Perlin noise.  The core algorithm is in optimized C.

# Installation

Make sure you have a C compiler installed.  The easiest way to do this is by installing Cython.

Then, install using the standard

    python setup.py install

This will compile the sources and install.

I have only tested this on Linux.

# Usage

To generate a Perlin noise-based video, follow two steps with the package.  First, generate the Perlin noise.  This is the most time consuming step, and will also use a lot of temporary disk space.  This is accomplished with:

```python
noise = perlstim.Perl(xsize=400, ysize=100, tdur=60*2, xyscale=.5, tscale=.01, seed=0)
```

Second, apply "filters" to the Perlin noise and save the resulting video.  Filters include thresholds, sync squares in the corner, etc.  If using a filter with no arguments, just pass a string naming the filter.  If using a filter with arguments, pass a tuple where the first element is the name of the filter as a string, and the remaining elements are the arguments.  For example,

```python
noise.save_video("noise.mp4", filters=["reverse", ("comb", .05)])
```

The above example applies the "reverse" filter (with no arguments) and the "comb" filter with the argument 0.1.

# Filters

The following filters are currently defined:

- "threshold" (1 argument): set all values above the threshold argument to white, and all below to black.
- "softthresh" (1 argument): set values much greater than 0 to white and much less than zero to blac.  Use shades of grey for intermediate values, according to a sigmoid with a temperature given as the argument.
- "comb" (1 argument): Alternate black and white thresholds at intervals given by the argument.
- "reverse" (0 arguments): play the video in reverse
- "invert" (0 arguments): switch white and black
- "wood" (1 argument): similar to "comb", but use a sawtooth wave
- "blur" (1 argument): Gaussian blur with the given spatial standard deviation
- "photodiode" (1 argument): Draw a sync square in the corner, with a size given by the argument.
- "photodiode_anywhere" (3 arguments): Draw a sync square at the coordinates given by the first two arguments (x and y), and of size given by argument 3.
- [any function] (0 arguments): If you pass a function, the function will be applied to each chunk of the pink noise video.  Chunks consist of the entire x and y but a subset of z, guaranteed to be an even number.

# Example

To get started, try the following:

```python
import perlstim
stim = perlstim.Perl(xsize=480, ysize=128, tdur=60*5, xyscale=.2, tscale=50)
stim.save_video("perlin_stimulus.mp4", loop=1, filters=[("comb", .08), ("photodiode", 30)])
```

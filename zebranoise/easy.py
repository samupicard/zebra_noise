import imageio
import warnings
from .util import generate_frames, filter_frames_index_function, apply_filters, discretize

def zebra_noise(output_file, xsize, ysize, tdur, levels=10, xyscale=.2, tscale=50, fps=30, xscale=1.0, yscale=1.0, seed=0, filters=[("comb", 0.08)]):
    tsize = int(tdur*fps)
    textra = (tscale - (tsize % tscale)) % tscale
    if textra > 0:
        warnings.warn(f"Adding {textra} extra timepoints to make tscale a multiple of tdur")
    tsize += textra
    get_index = filter_frames_index_function(filters, tsize)
    writer = imageio.get_writer(output_file, fps=fps)
    for _i in range(0, tsize):
        i = get_index(_i)
        frame = generate_frames(xsize, ysize, tsize, [i], levels=levels, xyscale=xyscale, tscale=tscale, xscale=xscale, yscale=yscale, seed=seed)
        filtered = apply_filters(frame[None], filters)[0] # TODO I don't think this will work with the photodiode filter
        disc = discretize(filtered[:,:,0])
        writer.append_data(disc)
    writer.close()

"""Reconstitute an analysis in a temporary directory on the current machine.

Handles copying or linking files into a work directory, running an analysis,
then handing off outputs to ship back to subsequent processing steps.
"""
import os
import uuid
import shutil

from bcbio import utils
from bcbio.log import logger
from bcbiovm.docker import remap

def prep_workdir(pack, parallel, args):
    """Unpack necessary files and directories into a temporary structure for processing
    """
    if pack["type"] == "shared":
        workdir, remap_dict, new_args = _create_workdir_shared(pack["workdir"], args, parallel, pack["tmpdir"])
        return workdir, new_args, _shared_finalizer(new_args, workdir, remap_dict, parallel)
    else:
        raise ValueError("Currently only handle shared filesystems")

def prep_datadir(pack):
    if "datadir" in pack:
        return pack["datadir"]
    else:
        raise ValueError("Need to handle unpacking biodata directory")

# ## Shared filesystem

def _remap_dict_shared(workdir, new_workdir, args):
    """Prepare a remap dictionary with directories we should potential copy files from.
    """
    ignore_keys = set(["algorithm"])
    out = {workdir: new_workdir}
    def _update_remap(fname, context, remap_dict):
        """Updated list of directories we should potentially be remapping in.
        """
        if not fname.startswith(tuple(out.keys())) and context and context[0] not in ignore_keys:
            dirname = os.path.normpath(os.path.dirname(fname))
            local_dir = utils.safe_makedir(os.path.join(new_workdir, "external", str(len(out))))
            out[dirname] = local_dir
    remap.walk_files(args, _update_remap, {})
    return out

def _create_workdir_shared(workdir, args, parallel, tmpdir=None):
    """Create a work directory given inputs from the shared filesystem.

    If tmpdir is not None, we create a local working directory within the
    temporary space so IO and processing occurs there, remapping the input
    argument paths at needed.
    """
    if not tmpdir:
        return workdir, {}, args
    else:
        new_workdir = utils.safe_makedir(os.path.join(tmpdir, "bcbio-work-%s" % uuid.uuid1()))
        remap_dict = _remap_dict_shared(workdir, new_workdir, args)
        new_args = remap.walk_files(args, _remap_copy_file(parallel), remap_dict)
        return new_workdir, remap_dict, new_args

def is_required_resource(context, parallel):
    fresources = parallel.get("fresources")
    if not fresources:
        return True
    for fresource in fresources:
        if context[:len(fresource)] == fresource:
            return True
    return False

def _remap_copy_file(parallel):
    """Remap file names and copy into temporary directory as needed.

    Handles simultaneous transfer of associated indexes.
    """
    def _do(fname, context, orig_to_temp):
        new_fname = remap.remap_fname(fname, context, orig_to_temp)
        if os.path.isfile(fname):
            if is_required_resource(context, parallel):
                logger.info("YES: %s: %s" % (context, fname))
                utils.safe_makedir(os.path.dirname(new_fname))
                for ext in ["", ".idx", ".gbi", ".tbi", ".bai"]:
                    if os.path.exists(fname + ext):
                        if not os.path.exists(new_fname + ext):
                            shutil.copyfile(fname + ext, new_fname + ext)
            else:
                logger.info("NO: %s: %s" % (context, fname))
        elif os.path.isdir(fname):
            utils.safe_makedir(new_fname)
        return new_fname
    return _do

def _shared_finalizer(args, workdir, remap_dict, parallel):
    """Cleanup temporary working directory, copying missing files back to the shared workdir.
    """
    def _do(out):
        if remap_dict:
            new_remap_dict = {v: k for k, v in remap_dict.items()}
            new_out = (remap.walk_files(out, _remap_copy_file(parallel), new_remap_dict)
                       if out else None)
            if os.path.exists(workdir):
                shutil.rmtree(workdir)
            return new_out
        else:
            return out
    return _do

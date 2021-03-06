"""Run individual tasks within the Clusterk framework.
"""
import os
import uuid

import yaml

from bcbio import utils
from bcbio.provenance import do
from bcbiovm.ship import pack

def runfn(fn_name, queue, wrap_args, parallel, run_args):
    """Run external function submitting to existing queue.
    """
    run_id = uuid.uuid4()
    work_dir = os.getcwd()
    script_file = "bcbio-%s-run.sh" % run_id
    arg_file = "bcbio-%s-args.json" % run_id
    parallel_file = "bcbio-%s-parallel.json" % run_id
    tarball = "bcbio-%s.tar.gz" % run_id
    run_args = pack.send_run(run_args, parallel["pack"])
    with utils.chdir(work_dir):
        with open(arg_file, "w") as out_handle:
            yaml.safe_dump(run_args, out_handle, default_flow_style=False, allow_unicode=False)
        with open(parallel_file, "w") as out_handle:
            yaml.safe_dump(parallel, out_handle, default_flow_style=False, allow_unicode=False)
        with open(script_file, "w") as out_handle:
            out_handle.write(_bootstrap_sh.format(fn_name=fn_name, arg_file=os.path.basename(arg_file),
                                                  parallel_file=os.path.basename(parallel_file)))
        do.run(["tar", "-czvpf", tarball, script_file, arg_file, parallel_file],
               "Prepare submission tarball")
        do.run(["ksub.py", "-q", queue["queue"], "-e", str(int(float(queue["mem"]) * 1024)),
                "-c", str(100 * int(queue["cores_per_job"])), "-u", os.path.abspath(tarball),
                os.path.basename(script_file)],
               "Submit to clusterk")
        for f in [script_file, arg_file, tarball]:
            os.remove(f)

_bootstrap_sh = """
# Bootstrap a bcbio-nextgen-vm installation on a bare Ubuntu machine
# Targets recent Ubuntu versions (Ubuntu 13.10, Ubuntu 14.04)

# Install Docker
sudo apt-key adv --keyserver keyserver.ubuntu.com --recv-keys 36A1D7869245C8950F966E92D8576A8BA88D21E9
sudo sh -c "echo deb http://get.docker.io/ubuntu docker main > /etc/apt/sources.list.d/docker.list"
sudo apt-get update
sudo apt-get install lxc-docker

# Install bcbio-nextgen-vm
sudo apt-get install wget
sudo mkdir /usr/local/share/bcbio-vm
sudo chown $USER /usr/local/share/bcbio-vm
wget http://repo.continuum.io/miniconda/Miniconda-latest-Linux-x86_64.sh
bash Miniconda-latest-Linux-x86_64.sh -b -p /usr/local/share/bcbio-vm/anaconda
/usr/local/share/bcbio-vm/anaconda/bin/conda install --yes \
    -c https://conda.binstar.org/collections/chapmanb/bcbio bcbio-nextgen-vm
sudo ln -s /usr/local/share/bcbio-vm/anaconda/bin/bcbio_vm.py /usr/local/bin/bcbio_vm.py
sudo bcbio_vm.py install --tools

# Run bcbio-vm
bcbio_vm.py runfn {fn_name} {parallel_file} {arg_file}
"""

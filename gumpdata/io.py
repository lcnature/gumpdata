import os
from os.path import join as _opj
import numpy as np
import csv

def _sub2id(sub):
    if isinstance(sub, int):
        return 'sub%.3i' % sub
    else:
        return 'sub%s' % sub

def _taskrun(task, run):
    return 'task%.3i_run%.3i' % (task, run)


class GumpData(object):
    def __init__(self, basedir=os.curdir):
        self._basedir = basedir


    def get_run_fmri(self, subj, task, run, flavor='dico'):
        """Returns a NiBabel image instance for fMRI of a particular run

        Parameters
        ----------
        subj : int or str
          Subject identifier (without 'sub' prefix).
        task : int
          Task ID (see task_key.txt)
        run : int
          Run ID.
        flavor : ('', 'dico', 'dico7Tad2grpbold7Tad', 'dico7Tad2grpbold7Tad_nl')
          fMRI data flavor to access (see dataset description)

        Returns
        -------
        NiBabel Nifti1Image
        """
        import nibabel as nb

        if flavor == '':
            fname = 'bold.nii.gz'
        elif flavor == 'dico':
            fname = 'bold_dico.nii.gz'
        else:
            fname = 'bold_dico_%s.nii.gz'
        fname = _opj(self._basedir, _sub2id(subj),
                     'BOLD', _taskrun(task, run),
                     fname)
        return nb.load(fname)


    def get_run_motion_estimates(self, subj, task, run):
        """Returns the motion correction estimates for a particular run

        Parameters
        ----------
        subj : int or str
          Subject identifier (without 'sub' prefix).
        task : int
          Task ID (see task_key.txt)
        run : int
          Run ID.

        Returns
        -------
        array
          Array of floats -- one row per fMRI volume, 6 columns (first three:
          translation X, Y, Z in mm, last three: rotation in deg)
        """
        fname = _opj(self._basedir, _sub2id(subj),
                     'BOLD', _taskrun(task, run),
                     'bold_dico_moco.txt')
        data = np.loadtxt(fname)
        return data

    def get_motion_estimates(self, subj, task, runs=(1,2,3,4,5,6,7,8),
                             truncate=4):
        """Returns the merged motion correction estimates for multiple runs.

        The temporal overlap between movie segments/runs is removed by truncating
        the end and front of adjacent runs by a configurable number of samples.

        Parameters
        ----------
        subj : int or str
          Subject identifier (without 'sub' prefix).
        task : int
          Task ID (see task_key.txt)
        runs : sequence
          Sequence ID for runs to consider. By default all 8 runs are used.
        truncate : int
          Number of samples/volumes to truncate at the edges of adjacent runs.

        Returns
        -------
        array
          Array of floats -- one row per fMRI volume, 6 columns (first three:
          translation X, Y, Z in mm, last three: rotation in deg)
        """
        data = []
        for i, r in enumerate(runs):
            rdata = self.get_run_motion_estimates(subj, task, r)
            if truncate and i > 0:
                # remove desired number samples at the front (except for first run)
                rdata = rdata[truncate:]
            if truncate and i < len(runs) - 1:
                # remove desired number samples at the end (except for last run)
                rdata = rdata[:-truncate]
            data.append(rdata)
        return np.vstack(data)

    def get_run_physio_data(self, subj, task, run, sensors=None):
        """Returns the physiological recording for a particular run

        Parameters
        ----------
        subj : int or str
          Subject identifier (without 'sub' prefix).
        task : int
          Task ID (see task_key.txt)
        run : int
          Run ID.
        sensors : None or tuple({'trigger', 'respiratory', 'cardiac', 'oxygen'})
          Selection and order of values to return.

        Returns
        -------
        array
          Array of floats -- one row per sample (100Hz), if ``sensors`` is None,
          4 columns are returned (trigger track, respiratory trace, cardiac trace,
          oxygen saturation). If ``sensors`` is specified the order of columns
          matches the order of the ``sensors`` sequence.
        """
        fname = _opj(self._basedir, 'sub%s' % subj, 'physio', _taskrun(task, run),
                    'physio.txt.gz')
        sensor_map = {
            'trigger': 0,
            'respiratory': 1,
            'cardiac': 2,
            'oxygen': 3
        }
        if not sensors is None:
            sensors = [sensor_map[s] for s in sensors]
        data = np.loadtxt(fname, usecols=sensors)
        return data

    def get_physio_data(self, subj, task, runs=(1,2,3,4,5,6,7,8),
                        truncate=4, sensors=None):
        """Returns the physiological recording for a particular run

        The temporal overlap between movie segments/runs is removed by truncating
        the end and front of adjacent runs by a configurable number of trigger
        intervals.

        Parameters
        ----------
        subj : int or str
          Subject identifier (without 'sub' prefix).
        task : int
          Task ID (see task_key.txt)
        runs : sequence
          Sequence ID for runs to consider. By default all 8 runs are used.
        truncate : int
          Number of trigger intervals to truncate at the edges of adjacent runs.
          Only 3, 4 and 5 are meaningful.
        sensors : None or tuple({'trigger', 'respiratory', 'cardiac', 'oxygen'})
          Selection and order of values to return.

        Returns
        -------
        array
          Array of floats -- one row per sample (100Hz), if ``sensors`` is None,
          4 columns are returned (trigger track, respiratory trace, cardiac trace,
          oxygen saturation). If ``sensors`` is specified the order of columns
          matches the order of the ``sensors`` sequence.
        """
        added_trigger = False
        if not sensors is None:
            if not 'trigger' in sensors:
                sensors = tuple(sensors) + ('trigger',)
                added_trigger = True
                trigger_mask = np.array([s != 'trigger' for s in sensors])
            trigger_column = sensors.index('trigger')
        else:
            trigger_column = 0
        data = []
        for i, r in enumerate(runs):
            rdata = get_run_physio_data(self._basedir, subj, task, r, sensors=sensors)
            triggers = rdata.T[trigger_column].nonzero()[0]
            if i > 0:
                # remove desired number samples at the front (except for first run)
                rdata = rdata[triggers[truncate]:]
            if i < len(runs) - 1:
                # remove desired number samples at the end (except for last run)
                rdata = rdata[:triggers[-truncate]]
            if added_trigger:
                data.append(rdata[:, trigger_mask])
            else:
                data.append(rdata)
        return np.vstack(data)

    def get_scene_boundaries(self):
        """Returns the boundaries between scenes in movie time

        Returns
        -------
        list(float)
          Timestamps are given in seconds.
        """
        fname = _opj(self._basedir, 'stimulus', 'task001',
                     'annotations', 'scenes.csv')
        cr = csv.reader(open(fname))
        ts = [float(line[0]) for line in cr]
        return ts

    def get_german_audiodescription_transcript(self):
        """Returns the transcript with star and end timestamps

        Returns
        -------
        array(float, float), list(str)
          The first return value is a 2-column array with start and end timestamp
          of each narration sequence. The second return value is a list with the
          corresponding transcripts in UTF8 encoding.

        """
        fname = _opj(self._basedir, 'stimulus', 'task001', 'annotations',
                    'german_audio_description.csv')
        cr = csv.reader(open(fname))
        transcripts = []
        ts = []
        for line in cr:
            ts.append([float(i) for i in line[:2]])
            transcripts.append(line[2])
        return np.array(ts), transcripts


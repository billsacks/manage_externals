"""

FIXME(bja, 2017-11) External and SourceTree have a circular dependancy!
"""

import errno
import logging
import os

from .externals_description import ExternalsDescription
from .externals_description import read_externals_description_file
from .externals_description import create_externals_description
from .repository_factory import create_repository
from .externals_status import ExternalStatus
from .utils import fatal_error, printlog
from .global_constants import EMPTY_STR, LOCAL_PATH_INDICATOR


class _External(object):
    """
    _External represents an external object in side a SourceTree
    """

    # pylint: disable=R0902

    def __init__(self, root_dir, name, ext_description):
        """Parse an external description file into a dictionary of externals.

        Input:

            root_dir : string - the root directory path where
            'local_path' is relative to.

            name : string - name of the ext_description object. may or may not
            correspond to something in the path.

            ext_description : dict - source ExternalsDescription object

        """
        self._name = name
        self._repo = None
        self._externals = EMPTY_STR
        self._externals_sourcetree = None
        # Parse the sub-elements

        # _path : local path relative to the containing source tree
        self._local_path = ext_description[ExternalsDescription.PATH]
        # _repo_dir : full repository directory
        repo_dir = os.path.join(root_dir, self._local_path)
        self._repo_dir_path = os.path.abspath(repo_dir)
        # _base_dir : base directory *containing* the repository
        self._base_dir_path = os.path.dirname(self._repo_dir_path)
        # repo_dir_name : base_dir_path + repo_dir_name = rep_dir_path
        self._repo_dir_name = os.path.basename(self._repo_dir_path)
        assert(os.path.join(self._base_dir_path, self._repo_dir_name)
               == self._repo_dir_path)

        self._required = ext_description[ExternalsDescription.REQUIRED]
        self._externals = ext_description[ExternalsDescription.EXTERNALS]
        if self._externals:
            self._create_externals_sourcetree()
        repo = create_repository(
            name, ext_description[ExternalsDescription.REPO])
        if repo:
            self._repo = repo

    def get_name(self):
        """
        Return the external object's name
        """
        return self._name

    def get_local_path(self):
        """
        Return the external object's path
        """
        return self._local_path

    def status(self):
        """
        If the repo destination directory exists, ensure it is correct (from
        correct URL, correct branch or tag), and possibly update the external.
        If the repo destination directory does not exist, checkout the correce
        branch or tag.
        If load_all is True, also load all of the the externals sub-externals.
        """

        stat = ExternalStatus()
        stat.path = self.get_local_path()
        if not self._required:
            stat.source_type = ExternalStatus.OPTIONAL
        elif self._local_path == LOCAL_PATH_INDICATOR:
            # LOCAL_PATH_INDICATOR, '.' paths, are standalone
            # component directories that are not managed by
            # checkout_externals.
            stat.source_type = ExternalStatus.STANDALONE
        else:
            # managed by checkout_externals
            stat.source_type = ExternalStatus.MANAGED

        ext_stats = {}

        if not os.path.exists(self._repo_dir_path):
            stat.sync_state = ExternalStatus.EMPTY
            msg = ('status check: repository directory for "{0}" does not '
                   'exist.'.format(self._name))
            logging.info(msg)
        else:
            if self._repo:
                self._repo.status(stat, self._repo_dir_path)

            if self._externals and self._externals_sourcetree:
                # we expect externals and they exist
                cwd = os.getcwd()
                # SourceTree expecteds to be called from the correct
                # root directory.
                os.chdir(self._repo_dir_path)
                ext_stats = self._externals_sourcetree.status(self._local_path)
                os.chdir(cwd)

        all_stats = {}
        # don't add the root component because we don't manage it
        # and can't provide useful info about it.
        if self._local_path != LOCAL_PATH_INDICATOR:
            # store the stats under tha local_path, not comp name so
            # it will be sorted correctly
            all_stats[stat.path] = stat

        if ext_stats:
            all_stats.update(ext_stats)

        return all_stats

    def verbose_status(self):
        """Display the verbose status to the user. This is just the raw output
        from the repository 'status' command.

        """
        if not os.path.exists(self._repo_dir_path):
            msg = ('status check: repository directory for "{0}" does not '
                   'exist!'.format(self._name))
            logging.info(msg)
        else:
            cwd = os.getcwd()
            os.chdir(self._repo_dir_path)
            if self._repo:
                self._repo.verbose_status(self._repo_dir_path)
            os.chdir(cwd)

    def checkout(self, load_all):
        """
        If the repo destination directory exists, ensure it is correct (from
        correct URL, correct branch or tag), and possibly update the external.
        If the repo destination directory does not exist, checkout the correce
        branch or tag.
        If load_all is True, also load all of the the externals sub-externals.
        """
        if load_all:
            pass
        # Make sure we are in correct location

        if not os.path.exists(self._repo_dir_path):
            # repository directory doesn't exist. Need to check it
            # out, and for that we need the base_dir_path to exist
            try:
                os.makedirs(self._base_dir_path)
            except OSError as error:
                if error.errno != errno.EEXIST:
                    msg = 'Could not create directory "{0}"'.format(
                        self._base_dir_path)
                    fatal_error(msg)

        if self._repo:
            self._repo.checkout(self._base_dir_path, self._repo_dir_name)

    def checkout_externals(self, load_all):
        """Checkout the sub-externals for this object
        """
        if self._externals:
            if not self._externals_sourcetree:
                self._create_externals_sourcetree()
            self._externals_sourcetree.checkout(load_all)

    def _create_externals_sourcetree(self):
        """
        """
        if not os.path.exists(self._repo_dir_path):
            # NOTE(bja, 2017-10) repository has not been checked out
            # yet, can't process the externals file. Assume we are
            # checking status before code is checkoud out and this
            # will be handled correctly later.
            return

        cwd = os.getcwd()
        os.chdir(self._repo_dir_path)
        if not os.path.exists(self._externals):
            # NOTE(bja, 2017-10) this check is redundent with the one
            # in read_externals_description_file!
            msg = ('External externals description file "{0}" '
                   'does not exist! In directory: {1}'.format(
                       self._externals, self._repo_dir_path))
            fatal_error(msg)

        externals_root = self._repo_dir_path
        model_data = read_externals_description_file(externals_root,
                                                     self._externals)
        externals = create_externals_description(model_data)
        self._externals_sourcetree = SourceTree(externals_root, externals)
        os.chdir(cwd)


class SourceTree(object):
    """
    SourceTree represents a group of managed externals
    """

    def __init__(self, root_dir, model):
        """
        Build a SourceTree object from a model description
        """
        self._root_dir = os.path.abspath(root_dir)
        self._all_components = {}
        self._required_compnames = []
        for comp in model:
            src = _External(self._root_dir, comp, model[comp])
            self._all_components[comp] = src
            if model[comp][ExternalsDescription.REQUIRED]:
                self._required_compnames.append(comp)

    def status(self, relative_path_base=LOCAL_PATH_INDICATOR):
        """Report the status components

        FIXME(bja, 2017-10) what do we do about situations where the
        user checked out the optional components, but didn't add
        optional for running status? What do we do where the user
        didn't add optional to the checkout but did add it to the
        status. -- For now, we run status on all components, and try
        to do the right thing based on the results....

        """
        load_comps = self._all_components.keys()

        summary = {}
        for comp in load_comps:
            printlog('{0}, '.format(comp), end='')
            stat = self._all_components[comp].status()
            for name in stat.keys():
                # check if we need to append the relative_path_base to
                # the path so it will be sorted in the correct order.
                if not stat[name].path.startswith(relative_path_base):
                    stat[name].path = os.path.join(relative_path_base,
                                                   stat[name].path)
                    # store under key = updated path, and delete the
                    # old key.
                    comp_stat = stat[name]
                    del stat[name]
                    stat[comp_stat.path] = comp_stat
            summary.update(stat)

        return summary

    def verbose_status(self):
        """Display verbose status to the user. This is just the raw output of
        the git and svn status commands.

        """
        load_comps = self._all_components.keys()
        for comp in load_comps:
            self._all_components[comp].verbose_status()

    def checkout(self, load_all, load_comp=None):
        """
        Checkout or update indicated components into the the configured
        subdirs.

        If load_all is True, recursively checkout all externals.
        If load_all is False, load_comp is an optional set of components to load.
        If load_all is True and load_comp is None, only load the required externals.
        """
        printlog('Checking out externals: ', end='')
        if load_all:
            load_comps = self._all_components.keys()
        elif load_comp is not None:
            load_comps = [load_comp]
        else:
            load_comps = self._required_compnames

        # checkout the primary externals
        for comp in load_comps:
            printlog('{0}, '.format(comp), end='')
            self._all_components[comp].checkout(load_all)
        printlog('')

        # now give each external an opportunitity to checkout it's externals.
        for comp in load_comps:
            self._all_components[comp].checkout_externals(load_all)

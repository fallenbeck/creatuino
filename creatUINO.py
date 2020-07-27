#!/usr/bin/env python3
#
# Script to prepare and write an SD card for the TonUINO.
#
# It uses a map file (usually map.csv) that defines which (music) files will
# go to the SD card and creates a file system structure containing
# directories and files that can be copied directly to the SD card.
#
# Requires Python version >= 3.4.
# Written 2020 by niels@devpresso.org

### Import python classes
# NOTE: There may be additional classes that will be imported on an as-needed
#       basis from the functions depending on it
import multiprocessing
import os
import pathlib
import pprint
import sys


# Set up logging
# By default we use logging here to print any messages
import logging
log_formatter = logging.Formatter('%(message)s')
loglevel = logging.ERROR
log = logging.getLogger(__name__)
log.setLevel(loglevel)


class SDCardWriter():

    # Will hold the configuration of this script
    config = None

    # Variables to store the values from the command line
    recode = False

    def __init__(self):
        """Initializer
        """
        # Set up the logging facility
        global log
        if len(log.handlers) == 0:
            stdout = logging.StreamHandler()
            stdout.setFormatter(log_formatter)
            log.addHandler(stdout)
            log.setLevel(loglevel)

        # When started from command line we need to carry out some additional
        # actions.
        if __name__ == "__main__":
            # Parse the arguments from the command line
            self.argparser()

            # Invoke the main() function
            self.main()


    def argparser(self):
        """Define the arguments for argparse.
        """
        import argparse

        description = "Script to prepare an SD card for a TonUINO box."
        epilog = "{my_name}, Python {py_version_maj}.{py_version_min}.{py_version_tiny}".format(
                my_name = self.__class__.__name__,
                py_version_maj = sys.version_info[0],
                py_version_min = sys.version_info[1],
                py_version_tiny = sys.version_info[2],
                )

        parser = argparse.ArgumentParser(
                description = description,
                epilog = "{epilog}".format(
                    epilog=epilog
                    ),
                conflict_handler = "resolve",
                formatter_class = argparse.ArgumentDefaultsHelpFormatter,
                )

        ###
        ### Define the arguments
        ###

        parser.add_argument(
                "-f",
                "--overwrite",
                action = "store_true",
                default = False,
                help = """Overwrite already existing music/media files.
                       Usually, output files will be skipped if they
                       already exist.""",
                )

        parser.add_argument(
                "-j",
                "--parallel_jobs",
                action = "store",
                metavar = "JOBS",
                type = int,
                default = multiprocessing.cpu_count(),
                help = """Number of parallel encoding jobs.
                       You can speed up the encoding process by starting
                       independed processes encoding each the media files.
                       The drawback is that a number too great may render
                       a system unresponsive. Choose the number of parallel
                       processes wisely depending on your computer system's
                       CPU cores and current workload.
                       By default the number of parallel jobs is set to the
                       number of available CPU cores. Set to 0 to not limit
                       the number of processes.""",
                )

        parser.add_argument(
                "-m",
                "--mapfile",
                action = "store",
                default = "map.csv",
                help = """Map file defining the mapping of input media files
                       to output media files on the SD card. The format of
                       the file are comma-separated values with one line
                       for each file or directory.
                       The values are separated by a colon (";").
                       The first column of each line represents the output
                       name while the second column respresents the name of
                       the input file.
                       If the input file name refers to a directory, the
                       output file name will be also treated as a directory.
                       The file names for each input file (from the input
                       directory) are created automatically.
                       If the input file name refers to a single file the
                       output file name will be treated as file name.""",
                )

        parser.add_argument(
                "-o",
                "--output-dir",
                action = "store",
                default = "./out",
                help = """Define custom output directory.
                       The output file/directory names in the map file define
                       relative file names to the output directory.
                       Directories and file names will be created in this
                       output directory. Giving the mount point if the
                       TonUINO SD card will directly write output files
                       to the SD card.""",
                )

        parser.add_argument(
                "-r",
                "--recode",
                action = "store_true",
                default = False,
                help = """Recode music files even if source and target
                       format are equal (i.e. mp3).""",
                )

        # Define options for logging
        parser.add_argument(
                "-v",
                "--verbose",
                action = "count",
                default = 0,
                help = """Increase output verbosity. This option can be given
                       multiple times to increase verbosity even more.""",
                )

        parser.add_argument(
                "--ffmpeg",
                action = "store",
                help = """ffmpeg binary to use for media encoding.
                       If not specified ffmpeg will be searched in the PATH.""",
                )

        parser.add_argument(
                "--ffmpeg-options",
                action = "store",
                default = "-vsync 0 -codec:a libmp3lame -b:a 192K -vn -sn -dn",
                help = """ffmpeg options to use during encoding.
                       Please refer to ffmpeg's man page to get the options
                       you want to use. The default here may work with
                       TonUINO boxes but might not be the best for you
                       personally.""",
                )

        ###
        ### Parse the arguments
        ###
        try:
            args = parser.parse_args()
        except Exception as e:
            # Write an error msg to stderr
            print("Error while parsing arguments: {error}".format(
                error = e,
                ),
                file = sys.stderr,
                )
            sys.exit(0)

        global log
        if args.verbose == 0:
            log.setLevel(logging.ERROR)
            log.__format__ = log_formatter
        elif args.verbose == 1:
            log.setLevel(logging.WARNING)
            log.__format__ = log_formatter
        elif args.verbose == 2:
            log.setLevel(logging.INFO)
            log.__format__ = log_formatter
        elif args.verbose == 3:
            log.setLevel(logging.DEBUG)
            log.__format__ = log_formatter
        else:
            log.setLevel(logging.DEBUG)

        log.info("Log level: {}".format(logging.getLevelName(log.level)))
        log.debug("Arguments received from command line: {}".format(sys.argv[1:]))
        log.debug(pprint.pformat(args))

        self.recode = args.recode
        self.overwrite = args.overwrite
        self.ffmpeg_bin = args.ffmpeg
        self.ffmpeg_options = args.ffmpeg_options
        self.jobs_max = args.parallel_jobs

        # Read the mapfile and get the list of 2-tuples representing the
        # files to encode
        self.files_to_encode = self._load_mapfile(args.mapfile)

        if len(self.files_to_encode) == 0:
            log.error("No files to encode.")
            #sys.exit(0)

        # We now know that we have a least one file to encode
        # (if it does not exist yet) so we need to make sure that the output
        # directory exists
        log.debug("Creating output dir {} if needed".format(
            args.output_dir
            ))
        output_dir = pathlib.Path(args.output_dir)
        output_dir.mkdir(
                parents = True,
                exist_ok = True,
                )

        #Namespace(ffmpeg=None, ffmpeg_options='-i coden a', mapfile='mapfile.csv', output_dir='./out', overwrite=False, parallel_jobs=4, recode=False, verbose=3)


    def _load_mapfile(self,
            filename: str,
            ) -> list:
        """Reads the contents of the map file and returns a list of 2-tuples
        representing media files that need to go to the output directory.

        The first element of the 2-tuple is the source file, the second
        element of the 2-tuple is the target file.

        This tuples can be handed over to the encoding function that can
        create system processes to run a media file's encoding independently
        from other encoding processes.

        :param filename:    Filename of the mapfile
        :type filename:     str
        :return:            list of files to encode
        :rtype:             [tuple]
        """
        mapfile = pathlib.Path(filename)
        if not mapfile.exists():
            log.error("Map file {} does not exist".format(filename))
            sys.exit(1)
        #if not mapfile.


        return []




    def _load_config(self,
            configfile: str,
            fatal_if_missing: bool = False,
            ):
        """Load the config file for the particular script.
        Configuration settings will be made available via the self.config
        variable.

        It is expected to find this configuration file in $CC_BASE/etc/.
        If the environment variable CC_BASE is not set, this function will
        make the script exit with return code 1. If the config file could
        not be read, it will exit with return code 2.

        :param configfile:          Name of the config file
        :type configfile:           str
        :param fatal_if_missing:    If True this function will terminate the script
        :type fatal_if_missing:     bool
        """
        cf = os.path.join(configfile)
        log.debug("Config file: {}".format(cf))

        config = None
        try:
            import configparser
            config = configparser.ConfigParser()
            config.read(cf)
        except Exception as e:
            printerr("Could not read config file {}:".format(cf, e))
            if fatal_if_missing:
                sys.exit(2)
            else:
                config = {}

        log.debug("Returning config: {}".format(config))
        return config


    def main(self):
        """The script's main function orchestrating everything else after
        the initialization has been completed.
        """
        ## Load the config file
        #self.config = self._load_config()

        #from pprint import pprint
        #pprint(self.config.items())
        #pprint("Read config: {}".format(self.config.items()))

        pass


if __name__ == '__main__':
    s = SDCardWriter()

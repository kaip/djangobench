#!/usr/bin/env python

"""
Run us some Django benchmarks.
"""

import os
import subprocess
import sys
import tempfile
import urllib

import argparse
from unipath import DIRS, FSPath as Path

import perf

BENCMARK_DIR = Path(__file__).parent.child('benchmarks')


class colorize(object):
    GOOD = '\033[92m'
    INSIGNIFICANT = '\033[94m'
    SIGNIFICANT = '\033[93m'
    BAD = '\033[91m'
    ENDC = '\033[0m'

    @classmethod
    def colorize(cls, color, text):
        return "%s%s%s" % (color, text, cls.ENDC)

    @classmethod
    def good(cls, text):
        return cls.colorize(cls.GOOD, text)

    @classmethod
    def significant(cls, text):
        return cls.colorize(cls.SIGNIFICANT, text)

    @classmethod
    def insignificant(cls, text):
        return cls.colorize(cls.INSIGNIFICANT, text)

    @classmethod
    def bad(cls, text):
        return cls.colorize(cls.BAD, text)

def colorize_benchmark_result(result):
    if isinstance(result, perf.BenchmarkResult):
        output = ''
        delta_min = result.delta_min
        if 'faster' in delta_min:
            delta_min = colorize.good(delta_min)
        elif 'slower' in result.delta_min:
            delta_min = colorize.bad(delta_min)
        output += "Min: %f -> %f: %s\n" % (result.min_base, result.min_changed, delta_min)

        delta_avg = result.delta_avg
        if 'faster' in delta_avg:
            delta_avg = colorize.good(delta_avg)
        elif 'slower' in delta_avg:
            delta_avg = colorize.bad(delta_avg)
        output += "Avg: %f -> %f: %s\n" % (result.avg_base, result.avg_changed, delta_avg)

        t_msg = result.t_msg
        if 'Not significant' in t_msg:
            t_msg = colorize.insignificant(t_msg)
        elif 'Significant' in result.t_msg:
            t_msg = colorize.significant(t_msg)
        output += t_msg

        delta_std = result.delta_std
        if 'larger' in delta_std:
            delta_std = colorize.bad(delta_std)
        elif 'smaller' in delta_std:
            delta_std = colorize.good(delta_std)
        output += "Stddev: %.5f -> %.5f: %s" %(result.std_base, result.std_changed, delta_std)
        output += result.get_timeline()
        return output
    else:
        return str(result)

def main(control, experiment, benchmarks, trials, benchmark_dir=BENCMARK_DIR):
    if benchmarks:
        print "Running benchmarks: %s" % " ".join(benchmarks)
    else:
        print "Running all benchmarks"

    control_label = get_django_version(control)
    experiment_label = get_django_version(experiment)
    print "Control: Django %s (in %s)" % (control_label, control)
    print "Experiment: Django %s (in %s)" % (experiment_label, experiment)
    print

    # Calculate the subshell envs that we'll use to execute the
    # benchmarks in.
    control_env = {
        'PYTHONPATH': ":".join([
            Path(benchmark_dir).absolute(),
            Path(control).parent.absolute(),
            Path(__file__).parent
        ]),
    }
    experiment_env = {
        'PYTHONPATH': ":".join([
            Path(benchmark_dir).absolute(),
            Path(experiment).parent.absolute(),
            Path(__file__).parent
        ]),
    }

    results = []

    for benchmark in discover_benchmarks(benchmark_dir):
        if not benchmarks or benchmark.name in benchmarks:
            print "Running '%s' benchmark ..." % benchmark.name
            settings_mod = '%s.settings' % benchmark.name
            control_env['DJANGO_SETTINGS_MODULE'] = settings_mod
            experiment_env['DJANGO_SETTINGS_MODULE'] = settings_mod

            control_data = run_benchmark(benchmark, trials, control_env)
            experiment_data = run_benchmark(benchmark, trials, experiment_env)

            options = argparse.Namespace(
                track_memory = False,
                diff_instrumentation = False,
                benchmark_name = benchmark.name,
                disable_timelines = True,
                control_label = control_label,
                experiment_label = experiment_label,
            )
            result = perf.CompareBenchmarkData(control_data, experiment_data, options)
            print colorize_benchmark_result(result)
            print

def discover_benchmarks(benchmark_dir):
    for app in Path(benchmark_dir).listdir(filter=DIRS):
        if app.child('benchmark.py').exists() and app.child('settings.py').exists():
            yield app

def run_benchmark(benchmark, trials, env):
    """
    Similar to perf.MeasureGeneric, but modified a bit for our purposes.
    """
    # Remove Pycs, then call the command once to prime the pump and
    # re-generate fresh ones This makes sure we're measuring as little of
    # Python's startup time as possible.
    perf.RemovePycs()
    command = [sys.executable, '%s/benchmark.py' % benchmark]
    perf.CallAndCaptureOutput(command, env, track_memory=False, inherit_env=[])

    # Now do the actual mesurements.
    data_points = []
    for i in range(trials):
        output = perf.CallAndCaptureOutput(command, env, track_memory=False, inherit_env=[])
        stdout, stderr, mem_usage = output
        data_points.extend(float(line) for line in stdout.splitlines())
    return perf.RawData(data_points, mem_usage, inst_output=stderr)

def get_django_version(djangodir):
    out, err, _ = perf.CallAndCaptureOutput(
        [sys.executable, '-c' 'import django; print django.get_version()'],
        env = {'PYTHONPATH': Path(djangodir).parent.absolute()}
    )
    return out.strip()

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--control',
        default = 'django-control/django',
        help = "Path to the Django code tree to use as control."
    )
    parser.add_argument(
        '--experiment',
        default = 'django-experiment/django',
        help = "Path to the Django version to use as experiment."
    )
    parser.add_argument(
        '-t', '--trials',
        type = int,
        default = 50,
        help = 'Number of times to run each benchmark.'
    )
    parser.add_argument(
        'benchmarks',
        metavar = 'name',
        default = None,
        help = "Benchmarks to be run.  Defaults to all.",
        nargs = '*'
    )
    args = parser.parse_args()
    main(args.control, args.experiment, args.benchmarks, args.trials)

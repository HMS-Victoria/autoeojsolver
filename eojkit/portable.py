"""Offline acceptance checks using synthetic data only."""
import tempfile
from .asm import CodeTester
from .tools import find_gpp

SAMPLE_CODE = '''#include <iostream>
#include <optional>
#include <vector>
#include <numeric>
int main() { long long a,b; std::cin>>a>>b;
std::optional<long long> n=a+b; std::cout<<*n<<"\\n"; }
'''


def local_check():
    compiler = find_gpp(force=True)
    with tempfile.TemporaryDirectory(prefix="eoj-selftest-") as folder:
        tester = CodeTester(gpp=compiler, workdir=folder)
        result = tester.build(SAMPLE_CODE, "selftest", quiet=True)
        ok = result.ok and tester.test_with_samples(result.exe_path, [
            {"input": "19 23\n", "output": "42\n"},
            {"input": "-3 8\n", "output": "5\n"},
        ], quiet=True)
        return {"ok": bool(ok), "compiler": compiler,
                "error": "" if ok else tester.error_report(),
                "details": tester.get_test_result_text()}


def offline_pipeline_check():
    from .pipeline import solve
    from .judge import SubmitResult

    class Site:
        logged_in = True
        submissions = 0

        def get_problem_info(self, *args, **kwargs):
            return {"title": "Synthetic sum", "samples": [{"input": "19 23\n", "output": "42\n"}]}

        def submit(self, *args, **kwargs):
            self.submissions += 1
            return SubmitResult(ok=True, url="https://example.invalid/synthetic")

    class Model:
        last_error = "Synthetic model unavailable"

        def generate_code(self, *args):
            return SAMPLE_CODE

        def regenerate_code(self, *args):
            return None

    results = {}
    with tempfile.TemporaryDirectory(prefix="eoj-flow-") as folder:
        site, model = Site(), Model()
        tester = CodeTester(workdir=folder)
        options = dict(eoj_client=site, solver=model, tester=tester,
                       skip_login=True, skip_analysis=True)
        outcome = solve("synthetic", skip_submit=True, **options)
        results["local_only"] = outcome.ok and outcome.tests_passed and not site.submissions
        outcome = solve("synthetic", **options)
        results["simulated_submit"] = outcome.ok and site.submissions == 1
        outcome = solve("synthetic", skip_test=True, **options)
        results["skip_test_blocked"] = outcome.status == "UNVERIFIED" and site.submissions == 1
        tester.gpp = None
        outcome = solve("synthetic", **options)
        results["missing_compiler_blocked"] = outcome.status == "UNVERIFIED" and site.submissions == 1
        model.generate_code = lambda *args: ""
        outcome = solve("synthetic", **options)
        results["model_failure"] = outcome.status == "FAIL_CODE" and site.submissions == 1
        site.get_problem_info = lambda *args, **kwargs: None
        outcome = solve("synthetic", **options)
        results["site_failure"] = outcome.status == "FAIL_FETCH" and site.submissions == 1
    return results

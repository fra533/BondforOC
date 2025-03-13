from bondforoc.validate_results_3 import *

def test_clean_doi():
    expected_result = '10.1162/qss_a_00292'
    result_with_url = clean_doi('https://doi.org/10.1162/qss_a_00292')
    assert expected_result == result_with_url

    result_without_url = clean_doi('10.1162/qss_a_00292')
    assert expected_result == result_without_url

    result_empty = clean_doi('')
    expected_result_empty = ''
    assert result_empty == expected_result_empty
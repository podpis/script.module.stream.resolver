# -*- coding: utf-8 -*-
#
#      Copyright (C) 2015 tknorris (Derived from Mikey1234's & Lambda's)
#
#  This Program is free software; you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation; either version 2, or (at your option)
#  any later version.
#
#  This Program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with XBMC; see the file COPYING.  If not, write to
#  the Free Software Foundation, 675 Mass Ave, Cambridge, MA 02139, USA.
#  http://www.gnu.org/copyleft/gpl.html
#
#  This code is a derivative of the YouTube plugin for XBMC and associated works
#  released under the terms of the GNU General Public License as published by
#  the Free Software Foundation; version 3

import re
import urllib
import urllib2
import urlparse
import util
import xbmc

MAX_TRIES = 3
COMPONENT = __name__


class NoRedirection(urllib2.HTTPErrorProcessor):

    def http_response(self, request, response):
        util.info('Stopping Redirect')
        return response

    https_response = http_response


def solve_equation(equation):
    try:
        offset = (1 if equation[0] == '+' else 0)
        return int(eval(equation.replace('!+[]', '1').replace('!![]',
                   '1').replace('[]', '0').replace('(', 'str(')[offset:]))
    except:
        pass


def solve(url, cj, user_agent=None, wait=True):
    if user_agent is None:
        user_agent = util.UA
    headers = {'User-Agent': user_agent, 'Referer': url}
    if cj is not None:
        try:
            cj.load(ignore_discard=True)
        except:
            pass
        opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(cj))
        urllib2.install_opener(opener)

    request = urllib2.Request(url)
    for key in headers:
        request.add_header(key, headers[key])
    try:
        response = urllib2.urlopen(request)
        html = response.read()
    except urllib2.HTTPError, e:
        html = e.read()

    tries = 0
    while tries < MAX_TRIES:
        solver_pattern = \
            'var (?:s,t,o,p,b,r,e,a,k,i,n,g|t,r,a),f,\s*([^=]+)'
        solver_pattern += \
            '={"([^"]+)":([^}]+)};.+challenge-form\'\);.*?\n.*?;(.*?);a\.value'
        vc_pattern = \
            'input type="hidden" name="jschl_vc" value="([^"]+)'
        pass_pattern = 'input type="hidden" name="pass" value="([^"]+)'
        init_match = re.search(solver_pattern, html, re.DOTALL)
        vc_match = re.search(vc_pattern, html)
        pass_match = re.search(pass_pattern, html)

        if not init_match or not vc_match or not pass_match:
            msg = \
                "Couldn't find attribute: init: |%s| vc: |%s| pass: |%s| No cloudflare check?"
            util.info(msg % (init_match, vc_match, pass_match))
            return False

        (init_dict, init_var, init_equation, equations) = \
            init_match.groups()
        vc = vc_match.group(1)
        password = pass_match.group(1)

        # util.info("VC is: %s" % (vc))

        varname = (init_dict, init_var)
        result = int(solve_equation(init_equation.rstrip()))
        util.info('Initial value: |%s| Result: |%s|' % (init_equation,
                  result))

        for equation in equations.split(';'):
            equation = equation.rstrip()
            if equation[:len('.'.join(varname))] != '.'.join(varname):
                util.info('Equation does not start with varname |%s|'
                          % equation)
            else:
                equation = equation[len('.'.join(varname)):]

            expression = equation[2:]
            operator = equation[0]
            if operator not in ['+', '-', '*', '/']:
                util.info('Unknown operator: |%s|' % equation)
                continue

            result = int(str(eval(str(result) + operator + str(solve_equation(
                expression)))))
            util.info('intermediate: %s = %s' % (equation, result))

        scheme = urlparse.urlparse(url).scheme
        domain = urlparse.urlparse(url).hostname
        result += len(domain)
        util.info('Final Result: |%s|' % result)

        if wait:
            util.info('Sleeping for 5 Seconds')
            xbmc.sleep(5000)

        url = \
            '%s://%s/cdn-cgi/l/chk_jschl?jschl_vc=%s&jschl_answer=%s&pass=%s' \
            % (scheme, domain, vc, result, urllib.quote(password))
        util.info('url: %s' % url)
        request = urllib2.Request(url)
        for key in headers:
            request.add_header(key, headers[key])
        try:
            opener = urllib2.build_opener(NoRedirection)
            urllib2.install_opener(opener)
            response = urllib2.urlopen(request)
            while response.getcode() in [301, 302, 303, 307]:
                if cj is not None:
                    cj.extract_cookies(response, request)

                redir_url = response.info().getheader('location')
                if not redir_url.startswith('http'):
                    base_url = '%s://%s' % (scheme, domain)
                    redir_url = urlparse.urljoin(base_url, redir_url)

                request = urllib2.Request(redir_url)
                for key in headers:
                    request.add_header(key, headers[key])
                if cj is not None:
                    cj.add_cookie_header(request)

                response = urllib2.urlopen(request)
            final = response.read()
            if 'cf-browser-verification' in final:
                util.info('CF Failure: html: %s url: %s' % (html, url))
                tries += 1
                html = final
            else:
                break
        except urllib2.HTTPError, e:
            util.info('CloudFlare HTTP Error: %s on url: %s' % (e.code,
                      url))
            return False
        except urllib2.URLError, e:
            util.info('CloudFlare URLError Error: %s on url: %s' % (e,
                      url))
            return False

    if cj is not None:
        util.cache_cookies()

    return final
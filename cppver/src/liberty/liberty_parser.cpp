#include "easysta/liberty/liberty_parser.hpp"

#include <cctype>
#include <cstdlib>
#include <stdexcept>

namespace easysta::liberty {

namespace {

struct Token {
    enum Type { Ident, Str, LParen, RParen, LBrace, RBrace, Comma, Colon, Semi, End } type;
    std::string text;
};

std::vector<Token> tokenize(const std::string& s) {
    std::vector<Token> tokens;
    size_t n = s.size();
    size_t i = 0;

    auto is_delim = [](char c) {
        return c == '(' || c == ')' || c == '{' || c == '}' || c == ',' ||
               c == ':' || c == ';' || c == '"';
    };

    while (i < n) {
        char c = s[i];

        if (std::isspace(static_cast<unsigned char>(c)) || c == '\\') {
            ++i;
            continue;
        }

        if (c == '/' && i + 1 < n && s[i + 1] == '*') {
            i += 2;
            while (i + 1 < n && !(s[i] == '*' && s[i + 1] == '/')) ++i;
            i = (i + 1 < n) ? i + 2 : n;
            continue;
        }

        if (c == '"') {
            size_t start = ++i;
            while (i < n && s[i] != '"') ++i;
            tokens.push_back({Token::Str, s.substr(start, i - start)});
            if (i < n) ++i; // skip closing quote
            continue;
        }

        switch (c) {
            case '(': tokens.push_back({Token::LParen, "("}); ++i; continue;
            case ')': tokens.push_back({Token::RParen, ")"}); ++i; continue;
            case '{': tokens.push_back({Token::LBrace, "{"}); ++i; continue;
            case '}': tokens.push_back({Token::RBrace, "}"}); ++i; continue;
            case ',': tokens.push_back({Token::Comma, ","}); ++i; continue;
            case ':': tokens.push_back({Token::Colon, ":"}); ++i; continue;
            case ';': tokens.push_back({Token::Semi, ";"}); ++i; continue;
            default: break;
        }

        size_t start = i;
        while (i < n && !std::isspace(static_cast<unsigned char>(s[i])) &&
               s[i] != '\\' && !is_delim(s[i]) &&
               !(s[i] == '/' && i + 1 < n && s[i + 1] == '*')) {
            ++i;
        }
        if (i > start) {
            tokens.push_back({Token::Ident, s.substr(start, i - start)});
        } else {
            // Stray character we don't recognize; skip it to avoid an infinite loop.
            ++i;
        }
    }

    tokens.push_back({Token::End, ""});
    return tokens;
}

class Parser {
public:
    explicit Parser(std::vector<Token> toks) : tokens_(std::move(toks)) {}

    const Token& peek() const { return tokens_[idx_]; }

    Token advance() {
        Token t = tokens_[idx_];
        if (idx_ + 1 < tokens_.size()) ++idx_;
        return t;
    }

    void expect(Token::Type type) {
        if (peek().type != type) {
            throw std::runtime_error("liberty parse error: unexpected token '" + peek().text + "'");
        }
        advance();
    }

    bool at_end() const { return peek().type == Token::End; }

    void parse_item(LibGroup& parent) {
        if (peek().type != Token::Ident) {
            // Skip anything unexpected rather than aborting the whole parse.
            advance();
            return;
        }
        std::string name = advance().text;

        if (peek().type == Token::LParen) {
            advance();
            std::vector<std::string> args;
            while (peek().type != Token::RParen && peek().type != Token::End) {
                if (peek().type == Token::Comma) {
                    advance();
                    continue;
                }
                args.push_back(advance().text);
            }
            expect(Token::RParen);

            if (peek().type == Token::LBrace) {
                advance();
                LibGroup g;
                g.group_name = name;
                g.args = args;
                while (peek().type != Token::RBrace && peek().type != Token::End) {
                    parse_item(g);
                }
                expect(Token::RBrace);
                parent.groups.push_back(std::move(g));
            } else if (peek().type == Token::Semi) {
                advance();
                LibAttribute a;
                a.name = name;
                a.is_complex = true;
                a.args = args;
                parent.attributes.push_back(std::move(a));
            }
        } else if (peek().type == Token::Colon) {
            advance();
            std::string value;
            if (peek().type == Token::Str || peek().type == Token::Ident) {
                value = advance().text;
            }
            if (peek().type == Token::Semi) advance();
            LibAttribute a;
            a.name = name;
            a.is_complex = false;
            a.value = value;
            parent.attributes.push_back(std::move(a));
        }
        // Anything else (bare identifier not followed by '(' or ':') is skipped.
    }

private:
    std::vector<Token> tokens_;
    size_t idx_ = 0;
};

} // namespace

std::vector<LibGroup> parse_liberty(const std::string& content) {
    Parser parser(tokenize(content));
    LibGroup root;
    root.group_name = "__root__";
    while (!parser.at_end()) {
        parser.parse_item(root);
    }
    return std::move(root.groups);
}

std::vector<const LibGroup*> get_groups(const LibGroup& g, const std::string& type_name) {
    std::vector<const LibGroup*> result;
    for (const auto& sub : g.groups) {
        if (sub.group_name == type_name) result.push_back(&sub);
    }
    return result;
}

std::optional<std::string> get_attr(const LibGroup& g, const std::string& name) {
    for (const auto& a : g.attributes) {
        if (!a.is_complex && a.name == name) return a.value;
    }
    return std::nullopt;
}

std::vector<std::vector<double>> get_array(const LibGroup& g, const std::string& name) {
    std::vector<std::vector<double>> result;
    for (const auto& a : g.attributes) {
        if (a.is_complex && a.name == name) {
            for (const auto& arg : a.args) {
                std::vector<double> row;
                size_t start = 0;
                while (start <= arg.size()) {
                    size_t comma = arg.find(',', start);
                    std::string tok = (comma == std::string::npos) ? arg.substr(start)
                                                                    : arg.substr(start, comma - start);
                    size_t b = tok.find_first_not_of(" \t");
                    if (b != std::string::npos) {
                        size_t e = tok.find_last_not_of(" \t");
                        row.push_back(std::strtod(tok.substr(b, e - b + 1).c_str(), nullptr));
                    }
                    if (comma == std::string::npos) break;
                    start = comma + 1;
                }
                result.push_back(std::move(row));
            }
            return result;
        }
    }
    return result;
}

} // namespace easysta::liberty

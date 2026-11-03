package com.acme.bank.repository;

import com.acme.bank.model.Account;
import java.util.List;

public interface AccountSearchRepository {
    List<Account> searchByOwner(String owner);
}

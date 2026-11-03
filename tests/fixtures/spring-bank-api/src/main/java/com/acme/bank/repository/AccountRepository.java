package com.acme.bank.repository;

import com.acme.bank.model.Account;
import org.springframework.data.jpa.repository.JpaRepository;

public interface AccountRepository extends JpaRepository<Account, Long>, AccountSearchRepository {
}
